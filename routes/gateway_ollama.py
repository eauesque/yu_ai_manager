"""Transparent Ollama proxy at /ollama/<backend_name>/*.

Clients set OLLAMA_HOST=http://<host>:<port>/ollama/<name> and all Ollama
API calls (native /api/* and OpenAI-compat /v1/*) are forwarded to the
registered backend.  Request and response bodies are streamed so that
large blobs (GB-range model files) are never fully buffered in memory.
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
from core.gateway.errors import openai_error
from core.gateway.scopes import Scope
from core.gateway.sd_proxy import filter_request_headers, filter_response_headers
from core.web.proxy_prefixes import proxy_origin_allowed

logger = logging.getLogger(__name__)
bp = Blueprint("gateway_ollama", __name__, url_prefix="/ollama")

# blob paths use a much longer timeout to support large uploads/downloads
_TIMEOUT_DEFAULT = httpx.Timeout(300.0, connect=5.0)
_TIMEOUT_BLOB    = httpx.Timeout(None,  connect=5.0)

_RESP_STRIP_EXTRA = frozenset({"content-length"})


def _bearer() -> str | None:
    return extract_bearer(request.headers.get("Authorization"), request.headers.get("x-api-key"))


def _resolve(name: str) -> tuple[str, str] | tuple[None, str]:
    from core.gateway.backend_registry import resolve_backend_by_name
    r = resolve_backend_by_name("ollama", name)
    if r.error_kind == "not_found":
        return None, f"ollama backend not found: {name!r}"
    return r.base_url, r.resolved_backend_id


def _forward_headers() -> dict[str, str]:
    return {k: v for k, v in request.headers if k.lower() != "host"}


def _filter_resp_headers(upstream_headers: dict) -> dict:
    h = filter_response_headers(upstream_headers)
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
    if not auth.has_scope(auth_result, Scope.OLLAMA_PROXY):
        return openai_error(
            "Insufficient scope", "insufficient_scope", 403, param=str(Scope.OLLAMA_PROXY)
        )

    base_url, resolved = _resolve(name)
    if base_url is None:
        return openai_error(resolved, "backend_not_found", 404, "server_error")

    target_url = f"{base_url.rstrip('/')}/{subpath}"
    timeout = _TIMEOUT_BLOB if subpath.startswith("api/blobs") else _TIMEOUT_DEFAULT
    req_headers = filter_request_headers(_forward_headers(), request.remote_addr or "")
    key_id: str = getattr(auth_result, "key_id", "") or ""
    t0 = time.monotonic()
    endpoint = f"/ollama/{name}/{subpath}"
    client_ip = request.remote_addr or ""
    method = request.method

    client = httpx.AsyncClient(timeout=timeout)
    stream_cm = client.stream(
        method,
        target_url,
        headers=req_headers,
        params=request.args,
        content=request.body,  # async generator — never buffered in memory
    )

    try:
        upstream = await stream_cm.__aenter__()
    except httpx.ConnectError:
        await client.aclose()
        _emit_audit(key_id, client_ip, endpoint, method, 502, t0, resolved)
        return openai_error(f"Ollama backend unreachable: {name!r}", "backend_unavailable", 502, "server_error")
    except httpx.TimeoutException:
        await client.aclose()
        _emit_audit(key_id, client_ip, endpoint, method, 504, t0, resolved)
        return openai_error(f"Ollama backend timed out: {name!r}", "backend_timeout", 504, "server_error")
    except Exception:
        await client.aclose()
        raise

    status_code = upstream.status_code
    resp_headers = _filter_resp_headers(dict(upstream.headers))
    content_type = upstream.headers.get("content-type", "application/octet-stream")

    async def _body():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await stream_cm.__aexit__(None, None, None)
            await client.aclose()
            _emit_audit(key_id, client_ip, endpoint, method, status_code, t0, resolved)

    return Response(_body(), status=status_code, headers=resp_headers, content_type=content_type)


def _emit_audit(
    key_id: str,
    client_ip: str,
    endpoint: str,
    method: str,
    status_code: int,
    t0: float,
    backend_id: str,
) -> None:
    try:
        writer = get_writer()
        if writer is not None:
            writer.emit(AuditRecord(
                request_id=str(uuid.uuid4()),
                timestamp=datetime.now(UTC),
                endpoint=endpoint,
                method=method,
                status_code=status_code,
                latency_ms=int((time.monotonic() - t0) * 1000),
                client_ip=client_ip,
                auth_key_id=key_id,
                backend_id=backend_id,
            ))
    except Exception:
        logger.debug("audit emit failed", exc_info=True)
