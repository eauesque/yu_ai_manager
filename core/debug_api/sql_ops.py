"""Readonly SQL query execution for debug API."""

import os
import re
from typing import Any

from core.services_core.db_api import get_readonly_db
from core.web.auth_restart import is_loopback_request

# Reject any SQL containing write/DDL keywords or dangerous statements
_WRITE_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|DETACH|REPLACE"
    r"|PRAGMA|WITH\s+RECURSIVE|REINDEX|VACUUM|SAVEPOINT|RELEASE"
    r"|BEGIN|COMMIT|ROLLBACK)\b",
    re.IGNORECASE,
)

# Whitelist: only allow SELECT statements
_SELECT_RE = re.compile(r"^\s*SELECT\b", re.IGNORECASE)


def readonly_query_payload(
    sql: str, limit: int = 100
) -> tuple[dict[str, Any], int]:
    """Execute a readonly SQL query and return rows as dicts.

    Returns (payload_dict, http_status).
    """
    if os.environ.get("YU_DEBUG_MODE", "0") != "1":
        return {"error": "debug mode not enabled", "code": "debug_disabled"}, 403

    # Additional safety: only allow from localhost
    try:
        if not is_loopback_request():
            return {"error": "debug API restricted to localhost", "code": "debug_localhost_only"}, 403
    except RuntimeError:
        pass  # Outside request context (e.g. CLI usage)

    sql = sql.strip()
    if not sql:
        return {"error": "empty sql", "code": "empty_sql"}, 400

    # Reject queries containing semicolons (prevent multi-statement execution)
    if ";" in sql.rstrip().rstrip(";"):
        return {"error": "multiple statements not allowed", "code": "multi_stmt_rejected"}, 400

    # Only allow SELECT statements (whitelist approach)
    if not _SELECT_RE.match(sql):
        return {"error": "only SELECT statements allowed", "code": "not_select"}, 400

    if _WRITE_RE.search(sql):
        return {"error": "write operations not allowed", "code": "write_rejected"}, 400

    limit = max(1, min(limit, 10000))

    con = get_readonly_db()
    try:
        cur = con.execute(sql)
        rows_raw = cur.fetchmany(limit + 1)
        columns: list[str] = [d[0] for d in cur.description] if cur.description else []
        truncated = len(rows_raw) > limit
        rows: list[dict[str, Any]] = [
            dict(zip(columns, r, strict=False)) for r in rows_raw[:limit]
        ]
        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
        }, 200
    except Exception as exc:
        return {"error": f"SQL error: {exc}", "code": "sql_error"}, 400
    # pooled connection: do not close
