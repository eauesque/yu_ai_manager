"""RPC server thread and dispatch logic for IsolatedExtensionProcess.

Handles worker -> main requests on the bounded read-only DB channel.
"""

from __future__ import annotations

import contextlib
import json
import logging
import sqlite3
import threading
import time
from typing import Any

from .ipc_protocol import (
    IPCError,
    deserialize_args,
    recv_msg,
    send_msg,
    serialize_args,
)

logger = logging.getLogger(__name__)
_MAX_DB_ROWS = 1000
_MAX_DB_RESULT_BYTES = 1024 * 1024
_MAX_DB_SQL_BYTES = 64 * 1024
_MAX_DB_QUERY_STEPS = 250_000
_DB_PROGRESS_GRANULARITY = 1_000
_MAX_DB_QUERY_SECONDS = 0.25
_BROKER_DENIED_FUNCTIONS = frozenset({"nfkc_lower", "regexp"})


def _broker_readonly_authorizer(action, arg1, arg2, database, trigger) -> int:
    """Apply the read-only policy and exclude host Python SQL functions."""
    from core.extensions_core.sandbox.sandbox_proxy import _readonly_authorizer

    if action == sqlite3.SQLITE_FUNCTION:
        function_name = (arg2 or arg1 or "").lower()
        if function_name in _BROKER_DENIED_FUNCTIONS:
            return sqlite3.SQLITE_DENY
    return _readonly_authorizer(action, arg1, arg2, database, trigger)


class IsolatedProcessRPCMixin:
    """Mixin providing RPC server and dispatch for IsolatedExtensionProcess.

    Expects the host class to have:
      - self._alive: bool
      - self._reverse_conn: Optional[socket.socket]
      - self.ext_name: str
      - self.is_alive() -> bool
    """

    def _start_rpc_server(self) -> threading.Thread | None:
        """Start the RPC server thread for handling worker requests."""
        if self._reverse_conn is None:
            return None
        thread = threading.Thread(
            target=self._handle_worker_requests,
            daemon=True,
            name=f"iso-rpc-{self.ext_name}",
        )
        thread.start()
        return thread

    def _handle_worker_requests(self) -> None:
        """Handle requests from the worker (e.g. ServiceRegistry.get).

        Runs on the reverse socket in a dedicated thread until the worker stops.
        """
        conn = self._reverse_conn
        if conn is None:
            return

        while self._alive:
            try:
                request = recv_msg(conn, timeout=5.0)
                if request is None:
                    if not self.is_alive():
                        break
                    continue

                response = self._dispatch_worker_request(request)
                send_msg(conn, response)
            except Exception:
                if not self._alive:
                    break

    def _dispatch_worker_request(self, request: dict) -> dict:
        """Dispatch a request received from the worker."""
        req_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params", {})

        try:
            if set(request) - {"jsonrpc", "method", "params", "id"}:
                raise IPCError("Unexpected RPC fields")
            if method == "db.query":
                result = self._handle_db_query(params)
                return {"jsonrpc": "2.0", "result": serialize_args(result), "id": req_id}

            return {
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": "Request rejected"},
                "id": req_id,
            }
        except Exception:
            logger.warning("%s: Rejected isolated worker RPC", self.ext_name, exc_info=True)
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32000, "message": "Request rejected"},
                "id": req_id,
            }

    def _handle_db_query(self, params: dict) -> list[dict]:
        """Run a bounded read-only query for this process's extension."""
        from core.extensions_core.sandbox.sandbox_proxy import (
            SandboxedConnection,
            SandboxedDB,
            _open_extension_readonly_db,
        )
        from core.extensions_core.service_registry import ServiceRegistry
        from core.extensions_core.token_mgmt.capability_token import get_enforcer

        if set(params) - {"sql", "params"}:
            raise IPCError("Unexpected DB query fields")
        spawned_db_permissions = {"db:read", "db:write"} & self.granted_permissions
        if not spawned_db_permissions:
            raise IPCError("DB permission denied")
        try:
            enforcer = get_enforcer()
            if not any(
                enforcer.has_permission(self.ext_name, permission)
                for permission in spawned_db_permissions
            ):
                raise IPCError("DB permission denied")
        except IPCError:
            raise
        except Exception as exc:
            raise IPCError("DB permission check failed") from exc
        sql = params.get("sql")
        values = deserialize_args(params.get("params", []))
        if not isinstance(sql, str) or not sql.lstrip().upper().startswith(("SELECT", "WITH")):
            raise IPCError("Only SELECT queries are allowed")
        if len(sql.encode("utf-8")) > _MAX_DB_SQL_BYTES:
            raise IPCError("DB query is too large")
        if not self._valid_db_params(values):
            raise IPCError("Invalid DB query parameters")

        service = ServiceRegistry.get("db", caller=self.ext_name)
        if not isinstance(service, SandboxedDB):
            raise IPCError("Sandboxed DB service unavailable")
        connection = SandboxedConnection(
            _open_extension_readonly_db(include_custom_functions=False),
            self.ext_name,
            False,
        )
        raw_connection = getattr(connection, "_real", None)
        if raw_connection is None or not all(
            hasattr(raw_connection, method) for method in ("setlimit", "set_progress_handler")
        ):
            connection.close()
            raise IPCError("Bounded DB service unavailable")
        try:
            raw_connection.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, _MAX_DB_SQL_BYTES)
            raw_connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, _MAX_DB_RESULT_BYTES)
            raw_connection.set_authorizer(_broker_readonly_authorizer)
            deadline = time.monotonic() + _MAX_DB_QUERY_SECONDS
            progress_calls = 0

            def interrupt_expensive_query() -> int:
                nonlocal progress_calls
                progress_calls += 1
                return int(
                    progress_calls * _DB_PROGRESS_GRANULARITY > _MAX_DB_QUERY_STEPS
                    or time.monotonic() > deadline
                )

            raw_connection.set_progress_handler(
                interrupt_expensive_query,
                _DB_PROGRESS_GRANULARITY,
            )
            cursor = connection.execute(sql, values)
            columns = [description[0] for description in (cursor.description or ())]
            rows = cursor.fetchmany(_MAX_DB_ROWS + 1)
            if len(rows) > _MAX_DB_ROWS:
                raise IPCError("DB result row limit exceeded")
            result = [dict(zip(columns, row, strict=True)) for row in rows]
            encoded = json.dumps(serialize_args(result), ensure_ascii=False).encode("utf-8")
            if len(encoded) > _MAX_DB_RESULT_BYTES:
                raise IPCError("DB result size limit exceeded")
            return result
        finally:
            with contextlib.suppress(Exception):
                raw_connection.set_progress_handler(None, 0)
            connection.close()

    @staticmethod
    def _valid_db_params(values: Any) -> bool:
        scalar = (str, int, float, bool, type(None))
        if isinstance(values, (list, tuple)):
            return all(isinstance(value, scalar) for value in values)
        if isinstance(values, dict):
            return all(
                isinstance(key, str) and isinstance(value, scalar)
                for key, value in values.items()
            )
        return False
