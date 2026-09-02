"""Transparent Gradio proxy at /gradio/<backend_name>/*.

Full pass-through with body size limit only.  No endpoint allow-list.
WebSocket (/queue/join) is not supported — HTTP-only.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime

import httpx
from quart import Blueprint, Response, request
from quart.typing import ResponseReturnValue

from core.gateway.audit import AuditRecord, get_writer
from core.gateway.auth import extract_bearer, get_auth
from core.gateway.errors import BodyTooLargeError, openai_error
from core.gateway.scopes import Scope
from core.gateway.sd_proxy import filter_request_headers, filter_response_headers
from core.gateway.streaming import iter_body_with_limit
from core.web.proxy_prefixes import proxy_origin_allowed

logger = logging.getLogger(__name__)
bp = Blueprint("gateway_gradio", __name__, url_prefix="/gradio")

_BODY_LIMIT = 50 * 1024 * 1024  # 50 MiB
_TIMEOUT = httpx.Timeout(300.0, connect=5.0)
_RESP_STRIP_EXTRA = frozenset({"content-length"})


def _bearer() -> str | None:
    return extract_bearer(request.headers.get("Authorization"), request.headers.get("x-api-key"))


def _resolve(name: str) -> tuple[str, str] | tuple[None, str]:
    from core.gateway.backend_registry import resolve_backend_by_name
    r = resolve_backend_by_name("gradio", name)
    if r.error_kind == "not_found":
        return None, f"gradio backend not found: {name!r}"
    return r.base_url, r.resolved_backend_id


def _filter_resp(headers: dict) -> dict:
    h = filter_response_headers(headers)
    return {k: v for k, v in h.items() if k.lower() not in _RESP_STRIP_EXTRA}


@bp.route("/<name>/<path:subpath>", methods=["GET", "POST", "PUT", "DELETE", "HEAD", "PATCH"])
async def proxy(name: str, subpath: str) -> ResponseReturnValue:
    if not proxy_origin_allowed(request):
        return openai_error("Forbidden", "forbidden", 403)

    auth = get_auth()
    auth_result = auth.check_request(
        bearer=_bearer(),
        remote_addr=request.remote_addr or "",
        allow_loopback_bypass=True,
    )
    if auth_result is None:
        return openai_error("Unauthorized", "invalid_api_key", 401, "authentication_error")
    if not auth.has_scope(auth_result, Scope.GRADIO_PROXY):
        return openai_error(
            "Insufficient scope", "insufficient_scope", 403, param=str(Scope.GRADIO_PROXY)
        )

    base_url, resolved = _resolve(name)
    if base_url is None:
        return openai_error(resolved, "backend_not_found", 404, "server_error")

    if any(seg == ".." for seg in subpath.split("/")):
        return openai_error("Forbidden", "forbidden", 403)

    if (request.content_length or 0) > _BODY_LIMIT:
        return openai_error("Body too large", "body_too_large", 413)

    target_url = f"{base_url.rstrip('/')}/{subpath}"
    req_headers = filter_request_headers(dict(request.headers), request.remote_addr or "")

    t0 = time.monotonic()
    status = 502
    resp_body = b""
    try:
        async with (
            httpx.AsyncClient(timeout=_TIMEOUT) as client,
            client.stream(
                request.method,
                target_url,
                headers=req_headers,
                content=iter_body_with_limit(request.body, _BODY_LIMIT),
                params=request.args,
            ) as upstream,
        ):
            resp_body = await upstream.aread()
            resp_headers = _filter_resp(dict(upstream.headers))
            status = upstream.status_code
    except BodyTooLargeError:
        return openai_error("Body too large", "body_too_large", 413)
    except httpx.ConnectError:
        return openai_error("gradio backend unavailable", "backend_unavailable", 502, "server_error")

    latency_ms = int((time.monotonic() - t0) * 1000)
    writer = get_writer()
    if writer:
        writer.emit(AuditRecord(
            request_id=str(uuid.uuid4()),
            timestamp=datetime.now(UTC),
            client_ip=request.remote_addr or "",
            auth_key_id=auth_result.key_id,
            endpoint=f"/{subpath}",
            method=request.method,
            status_code=status,
            latency_ms=latency_ms,
            backend_id=resolved,
            request_bytes=request.content_length,
            response_bytes=len(resp_body),
        ))

    return Response(resp_body, status=status, headers=resp_headers)
