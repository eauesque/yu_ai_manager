from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import time
import uuid
from datetime import UTC, datetime
from urllib.parse import urlencode

import httpx
import websockets  # type: ignore[import]
from quart import Blueprint, Response, request, websocket

from core.gateway.audit import AuditRecord, get_writer
from core.gateway.auth import extract_bearer, get_auth
from core.gateway.comfy_proxy import (
    extract_bearer_from_subprotocols,
    get_comfy_scope,
    validate_client_id,
    validate_view_params,
)
from core.gateway.errors import BodyTooLargeError, openai_error
from core.gateway.scopes import Scope
from core.gateway.sd_proxy import filter_request_headers, filter_response_headers
from core.gateway.streaming import iter_body_with_limit
from core.infra_core.api_errors import api_error
from core.web.proxy_prefixes import proxy_origin_allowed

logger = logging.getLogger(__name__)
bp = Blueprint("gateway_comfy", __name__, url_prefix="/comfy")

_PROMPT_LIMIT = 5 * 1024 * 1024
_UPLOAD_LIMIT = 50 * 1024 * 1024
_DEFAULT_LIMIT = 1 * 1024 * 1024
_WS_IDLE_TIMEOUT = 120.0
_AUTH_QUERY_KEYS = frozenset({"token", "api_key", "bearer"})


class _BytesAsBody:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self._done = False

    def __aiter__(self):
        return self

    async def __anext__(self) -> bytes:
        if self._done:
            raise StopAsyncIteration
        self._done = True
        return self._data


def _bearer() -> str | None:
    return extract_bearer(request.headers.get("Authorization"), request.headers.get("x-api-key"))


def _resolve_comfy(req) -> tuple[str, str, None] | tuple[None, str, int]:
    """Returns (base_url, resolved_id, None) or (None, error_message, status_code)."""
    from core.gateway.backend_registry import resolve_backend

    backend_id = req.headers.get("X-Backend-Id") or None
    r = resolve_backend("comfyui", backend_id)
    if r.error_kind == "not_found":
        return None, f"backend not found: {backend_id}", 404
    if r.error_kind == "type_mismatch":
        return None, f"type mismatch: {backend_id}", 400
    return r.base_url, r.resolved_backend_id, None


def _to_ws_base(base_url: str) -> str:
    if base_url.startswith("https://"):
        return "wss://" + base_url[len("https://"):].rstrip("/")
    if base_url.startswith("http://"):
        return "ws://" + base_url[len("http://"):].rstrip("/")
    return base_url.rstrip("/")


@bp.route("/api/<path:subpath>", methods=["GET", "POST"])
async def comfy_proxy(subpath: str):
    if not proxy_origin_allowed(request):
        return openai_error("Forbidden", "forbidden", 403)
    path = f"/{subpath}"
    method = request.method
    scope_needed = get_comfy_scope(method, path)
    if scope_needed is None:
        return Response(status=404)

    auth = get_auth()
    result = auth.check_request(
        bearer=_bearer(),
        remote_addr=request.remote_addr or "",
        allow_loopback_bypass=True,
    )
    if result is None:
        return openai_error("Unauthorized", "invalid_api_key", 401, "authentication_error")
    if not auth.has_scope(result, scope_needed):
        return openai_error("Insufficient scope", "insufficient_scope", 403, param=str(scope_needed))

    # /view path traversal guard
    if path == "/view":
        err = validate_view_params(
            request.args.get("filename", ""),
            request.args.get("subfolder", ""),
            request.args.get("type", ""),
        )
        if err:
            return openai_error("Invalid path parameters", "path_traversal", 400)

    limit = (
        _PROMPT_LIMIT if path == "/prompt"
        else _UPLOAD_LIMIT if path.startswith("/upload")
        else _DEFAULT_LIMIT
    )
    if (request.content_length or 0) > limit:
        return openai_error("Body too large", "body_too_large", 413)

    base_url, resolved_id, err_code = _resolve_comfy(request)
    if base_url is None:
        assert err_code is not None
        return api_error(resolved_id, err_code)

    workflow_sha256 = None
    node_types = None
    if path == "/prompt":
        try:
            raw = await request.get_data()
            wf = json.loads(raw)
            prompt_dict = wf.get("prompt", wf)
            wf_json = json.dumps(prompt_dict, sort_keys=True, ensure_ascii=False)
            workflow_sha256 = hashlib.sha256(wf_json.encode()).hexdigest()
            node_types = [
                str(v["class_type"]) for v in prompt_dict.values()
                if isinstance(v, dict) and isinstance(v.get("class_type"), str)
            ]
            body_iter = _BytesAsBody(raw)
        except Exception:
            body_iter = request.body
    else:
        body_iter = request.body

    upstream_headers = {
        k: v for k, v in request.headers
        if k.lower() != "x-backend-id"
    }
    req_headers = filter_request_headers(upstream_headers, request.remote_addr or "")
    # For /view, only forward validated params
    if path == "/view":
        forward_params = {
            k: v for k, v in request.args.items()
            if k in ("filename", "subfolder", "type")
        }
    else:
        forward_params = dict(request.args)

    t0 = time.monotonic()
    status = 502
    resp_body = b""
    resp_headers: dict = {}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(1800.0, connect=5.0)) as client, client.stream(
            method,
            base_url.rstrip("/") + path,
            headers=req_headers,
            content=iter_body_with_limit(body_iter, limit),
            params=forward_params,
        ) as upstream:
            resp_body = await upstream.aread()
            resp_headers = filter_response_headers(dict(upstream.headers))
            status = upstream.status_code
    except BodyTooLargeError:
        return openai_error("Body too large", "body_too_large", 413)
    except httpx.ConnectError:
        return openai_error("ComfyUI unavailable", "backend_unavailable", 502, "server_error")

    latency_ms = int((time.monotonic() - t0) * 1000)
    comfy_prompt_id = None
    if path == "/prompt":
        with contextlib.suppress(Exception):
            comfy_prompt_id = json.loads(resp_body).get("prompt_id")

    writer = get_writer()
    if writer and result:
        writer.emit(AuditRecord(
            request_id=str(uuid.uuid4()),
            timestamp=datetime.now(UTC),
            client_ip=request.remote_addr or "",
            auth_key_id=result.key_id,
            endpoint=path,
            method=method,
            status_code=status,
            latency_ms=latency_ms,
            backend_id=resolved_id,
            workflow_sha256=workflow_sha256,
            node_types=node_types,
            comfy_prompt_id=comfy_prompt_id,
        ))
    return Response(resp_body, status=status, headers=resp_headers)


@bp.websocket("/ws")
async def comfy_ws():
    for key in _AUTH_QUERY_KEYS:
        if websocket.args.get(key):
            await websocket.close(4401, "auth required")
            return

    subprotocols = list(websocket.requested_subprotocols or [])
    token, remaining = extract_bearer_from_subprotocols(subprotocols)

    auth = get_auth()
    result = auth.check_bearer(token, remote_addr=websocket.remote_addr or "")
    if result is None:
        await websocket.close(4401, "auth required")
        return
    if not auth.has_scope(result, Scope.COMFY_GENERATE):
        await websocket.close(4403, "insufficient scope")
        return

    client_id = websocket.args.get("clientId", "")
    if client_id and not validate_client_id(client_id):
        await websocket.close(4400, "invalid request")
        return

    from core.gateway.backend_registry import resolve_backend

    backend_id = websocket.args.get("backend_id") or None
    r = resolve_backend("comfyui", backend_id)
    if r.error_kind == "not_found":
        await websocket.close(4404, f"backend not found: {backend_id}")
        return
    if r.error_kind == "type_mismatch":
        await websocket.close(4400, f"type mismatch: {backend_id}")
        return

    forward_params = [
        (k, v) for k, v in websocket.args.items(multi=True)
        if k != "backend_id"
    ]
    query = urlencode(forward_params)
    upstream_url = _to_ws_base(r.base_url) + "/ws"
    if query:
        upstream_url = f"{upstream_url}?{query}"
    try:
        async with websockets.connect(
            upstream_url,
            subprotocols=remaining or None,
        ) as upstream_ws:
            await websocket.accept(subprotocol=None)

            async def c2u():
                while True:
                    data = await asyncio.wait_for(websocket.receive(), timeout=_WS_IDLE_TIMEOUT)
                    await upstream_ws.send(data)

            async def u2c():
                async for msg in upstream_ws:
                    await websocket.send(msg)

            try:
                await asyncio.gather(c2u(), u2c(), return_exceptions=False)
            except TimeoutError:
                await websocket.close(4408, "idle timeout")
            except Exception:
                logger.warning("comfy gateway step failed", exc_info=True)
    except Exception as exc:
        logger.warning("[gateway:comfy_ws] upstream connect failed: %s", exc)
