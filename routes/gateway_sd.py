from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import uuid
from datetime import UTC, datetime
from urllib.parse import quote, unquote

import httpx
from quart import Blueprint, Response, request

from core.gateway.audit import AuditRecord, get_writer
from core.gateway.auth import extract_bearer, get_auth
from core.gateway.errors import BodyTooLargeError, openai_error
from core.gateway.scopes import Scope
from core.gateway.sd_proxy import filter_request_headers, filter_response_headers, get_sd_scope
from core.gateway.streaming import iter_body_with_limit
from core.infra_core.api_errors import api_error
from core.web.proxy_prefixes import proxy_origin_allowed

logger = logging.getLogger(__name__)
bp = Blueprint("gateway_sd", __name__, url_prefix="/sd")

_LIMITS: dict[str, int] = {
    "/sdapi/v1/txt2img":            5 * 1024 * 1024,
    "/sdapi/v1/img2img":           50 * 1024 * 1024,
    "/sdapi/v1/extra-single-image": 50 * 1024 * 1024,
}
_DEFAULT_LIMIT = 1 * 1024 * 1024
_GRADIO4_ALLOWED_API_NAMES = frozenset({
    "txt2img", "img2img", "interrogate",
})
_GRADIO4_LIMITS: dict[str, int] = {
    "txt2img":      5 * 1024 * 1024,
    "img2img":     50 * 1024 * 1024,
    "interrogate": 5 * 1024 * 1024,
}
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)


class _BytesAsBody:
    """Wrap pre-read bytes so iter_body_with_limit can consume them."""

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


def _check_auth(scope_needed: Scope) -> Response | None:
    if not proxy_origin_allowed(request):
        return openai_error("Forbidden", "forbidden", 403)
    auth = get_auth()
    result = auth.check_request(
        bearer=_bearer(),
        remote_addr=request.remote_addr or "",
        allow_loopback_bypass=True,
    )
    if result is None:
        return openai_error("Unauthorized", "invalid_api_key", 401, "authentication_error")
    if not auth.has_scope(result, scope_needed):
        return openai_error(
            "Insufficient scope", "insufficient_scope", 403, param=str(scope_needed)
        )
    return None


def _resolve_sd(req, *, from_query: bool = False) -> tuple[str, str, None] | tuple[None, str, int]:
    """Returns (base_url, resolved_id, None) or (None, error_message, status_code)."""
    from core.gateway.backend_registry import resolve_backend

    if from_query:
        backend_id = req.args.get("backend_id") or req.headers.get("X-Backend-Id") or None
    else:
        backend_id = req.headers.get("X-Backend-Id") or None
    r = resolve_backend("sd_webui", backend_id)
    if r.error_kind == "not_found":
        return None, f"backend not found: {backend_id}", 404
    if r.error_kind == "type_mismatch":
        return None, f"type mismatch: {backend_id}", 400
    return r.base_url, r.resolved_backend_id, None


def _request_headers_without_backend_id() -> dict[str, str]:
    return {
        k: v for k, v in request.headers
        if k.lower() != "x-backend-id"
    }


async def _proxy_to_sd(
    *,
    method: str,
    base_url: str,
    path: str,
    limit: int = _DEFAULT_LIMIT,
    params: dict[str, str] | None = None,
    body_iter: object | None = None,
) -> Response:
    req_headers = filter_request_headers(_request_headers_without_backend_id(), request.remote_addr or "")
    kwargs: dict[str, object] = {
        "headers": req_headers,
        "params": dict(request.args) if params is None else params,
    }
    if body_iter is not None:
        kwargs["content"] = iter_body_with_limit(body_iter, limit)

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(1800.0, connect=5.0)) as client, client.stream(
            method,
            base_url.rstrip("/") + path,
            **kwargs,
        ) as upstream:
            resp_body = await upstream.aread()
            resp_headers = filter_response_headers(dict(upstream.headers))
            return Response(resp_body, status=upstream.status_code, headers=resp_headers)
    except BodyTooLargeError:
        return openai_error("Body too large", "body_too_large", 413)
    except httpx.ConnectError:
        return openai_error("SD WebUI unavailable", "backend_unavailable", 502, "server_error")


async def _stream_from_sd(
    *,
    method: str,
    base_url: str,
    path: str,
    params: dict[str, str],
) -> Response:
    req_headers = filter_request_headers(_request_headers_without_backend_id(), request.remote_addr or "")
    client = httpx.AsyncClient(timeout=httpx.Timeout(1800.0, connect=5.0))
    stream_cm = client.stream(
        method,
        base_url.rstrip("/") + path,
        headers=req_headers,
        params=params,
    )
    try:
        upstream = await stream_cm.__aenter__()
    except httpx.ConnectError:
        await client.aclose()
        return openai_error("SD WebUI unavailable", "backend_unavailable", 502, "server_error")
    except Exception:
        await client.aclose()
        raise

    async def body_stream():
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await stream_cm.__aexit__(None, None, None)
            await client.aclose()

    resp_headers = filter_response_headers(dict(upstream.headers))
    return Response(body_stream(), status=upstream.status_code, headers=resp_headers)


@bp.route("/sdapi/v1/<path:subpath>", methods=["GET", "POST"])
async def sd_proxy(subpath: str):
    if not proxy_origin_allowed(request):
        return openai_error("Forbidden", "forbidden", 403)
    path = f"/sdapi/v1/{subpath}"
    method = request.method
    scope_needed = get_sd_scope(method, path)
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
        return openai_error(
            "Insufficient scope", "insufficient_scope", 403, param=str(scope_needed)
        )

    limit = _LIMITS.get(path, _DEFAULT_LIMIT)
    if (request.content_length or 0) > limit:
        return openai_error("Body too large", "body_too_large", 413)

    base_url, resolved_id, err_code = _resolve_sd(request)
    if base_url is None:
        assert err_code is not None
        return api_error(resolved_id, err_code)

    # Compute prompt_sha256 for generation endpoints
    prompt_sha256 = None
    if path in ("/sdapi/v1/txt2img", "/sdapi/v1/img2img"):
        try:
            raw = await request.get_data()
            body_dict = json.loads(raw)
            text = f"P\n{body_dict.get('prompt', '')}\nN\n{body_dict.get('negative_prompt', '')}"
            prompt_sha256 = hashlib.sha256(text.encode()).hexdigest()
            body_iter = _BytesAsBody(raw)
        except Exception:
            body_iter = request.body
    else:
        body_iter = request.body

    req_headers = filter_request_headers(_request_headers_without_backend_id(), request.remote_addr or "")
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
            params=request.args,
        ) as upstream:
            resp_body = await upstream.aread()
            resp_headers = filter_response_headers(dict(upstream.headers))
            status = upstream.status_code
    except BodyTooLargeError:
        return openai_error("Body too large", "body_too_large", 413)
    except httpx.ConnectError:
        return openai_error("SD WebUI unavailable", "backend_unavailable", 502, "server_error")

    latency_ms = int((time.monotonic() - t0) * 1000)
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
            prompt_sha256=prompt_sha256,
            request_bytes=request.content_length,
            response_bytes=len(resp_body),
        ))
    return Response(resp_body, status=status, headers=resp_headers)


@bp.route("/call/<api_name>", methods=["POST"])
async def gradio4_call(api_name: str):
    """Gradio4 generation submit. api_name must be in allowlist."""
    auth_error = _check_auth(Scope.SD_GENERATE)
    if auth_error is not None:
        return auth_error
    if api_name not in _GRADIO4_ALLOWED_API_NAMES:
        return api_error(f"api_name not allowed: {api_name}", 404)
    base_url, resolved_id, err_code = _resolve_sd(request)
    if base_url is None:
        assert err_code is not None
        return api_error(resolved_id, err_code)
    limit = _GRADIO4_LIMITS.get(api_name, _DEFAULT_LIMIT)
    body = await request.get_data(cache=False)
    if len(body) > limit:
        return api_error("payload too large", 413)
    return await _proxy_to_sd(
        method="POST",
        base_url=base_url,
        path=f"/call/{api_name}",
        limit=limit,
        body_iter=_BytesAsBody(body),
    )


@bp.route("/call/<api_name>/<event_id>", methods=["GET"])
async def gradio4_result(api_name: str, event_id: str):
    """SSE result fetch. ?backend_id query used for routing (EventSource compatible)."""
    auth_error = _check_auth(Scope.SD_QUERY)
    if auth_error is not None:
        return auth_error
    if api_name not in _GRADIO4_ALLOWED_API_NAMES:
        return api_error(f"api_name not allowed: {api_name}", 404)
    if not _UUID_RE.match(event_id):
        return api_error("invalid event_id", 400)
    base_url, resolved_id, err_code = _resolve_sd(request, from_query=True)
    if base_url is None:
        assert err_code is not None
        return api_error(resolved_id, err_code)
    params = {k: v for k, v in request.args.items() if k != "backend_id"}
    return await _stream_from_sd(
        method="GET",
        base_url=base_url,
        path=f"/call/{api_name}/{event_id}",
        params=params,
    )


@bp.route("/file=<path:filepath>", methods=["GET"])
async def gradio4_file(filepath: str):
    """Image file fetch. Path traversal protected."""
    auth_error = _check_auth(Scope.SD_QUERY)
    if auth_error is not None:
        return auth_error
    decoded = unquote(filepath)
    parts = decoded.replace("\\", "/").split("/")
    if any(p in ("..", "") or "\x00" in p for p in parts) or decoded.startswith("/"):
        return api_error("invalid path", 400)
    clean = "/".join(p for p in parts if p)
    base_url, resolved_id, err_code = _resolve_sd(request, from_query=True)
    if base_url is None:
        assert err_code is not None
        return api_error(resolved_id, err_code)
    params = {k: v for k, v in request.args.items() if k != "backend_id"}
    return await _proxy_to_sd(
        method="GET",
        base_url=base_url,
        path=f"/file={quote(clean, safe='/')}",
        params=params,
    )


@bp.route("/config", methods=["GET"])
@bp.route("/info", methods=["GET"])
@bp.route("/internal/ping", methods=["GET"])
async def gradio4_info():
    """Gradio4 schema/info/ping - needed for API type detection."""
    auth_error = _check_auth(Scope.SD_QUERY)
    if auth_error is not None:
        return auth_error
    base_url, resolved_id, err_code = _resolve_sd(request, from_query=True)
    if base_url is None:
        assert err_code is not None
        return api_error(resolved_id, err_code)
    params = {k: v for k, v in request.args.items() if k != "backend_id"}
    path = request.path[len("/sd"):] if request.path.startswith("/sd") else request.path
    return await _proxy_to_sd(
        method="GET",
        base_url=base_url,
        path=path,
        params=params,
    )


@bp.route("/internal/progress", methods=["POST"])
async def gradio4_progress():
    """Gradio4 progress check."""
    auth_error = _check_auth(Scope.SD_QUERY)
    if auth_error is not None:
        return auth_error
    base_url, resolved_id, err_code = _resolve_sd(request, from_query=True)
    if base_url is None:
        assert err_code is not None
        return api_error(resolved_id, err_code)
    params = {k: v for k, v in request.args.items() if k != "backend_id"}
    return await _proxy_to_sd(
        method="POST",
        base_url=base_url,
        path="/internal/progress",
        params=params,
        body_iter=request.body,
    )


@bp.route("/cancel", methods=["POST"])
async def gradio4_cancel():
    """Gradio4 cancel."""
    auth_error = _check_auth(Scope.SD_GENERATE)
    if auth_error is not None:
        return auth_error
    base_url, resolved_id, err_code = _resolve_sd(request, from_query=True)
    if base_url is None:
        assert err_code is not None
        return api_error(resolved_id, err_code)
    params = {k: v for k, v in request.args.items() if k != "backend_id"}
    return await _proxy_to_sd(
        method="POST",
        base_url=base_url,
        path="/cancel",
        params=params,
        body_iter=request.body,
    )
