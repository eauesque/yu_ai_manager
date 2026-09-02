from __future__ import annotations

import json
import logging
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from urllib.parse import unquote

import httpx
from quart import Blueprint, Response, current_app, request, session

from core.gateway.agentmemory_proxy import (
    build_request_headers,
    filter_response_headers,
    get_body_limit,
    get_upstream_base_url,
)
from core.gateway.agentmemory_proxy import (
    configure as _configure_proxy,
)
from core.gateway.agentmemory_proxy import (
    validate_base_url as _validate_base_url,
)
from core.gateway.audit import AuditRecord, get_writer
from core.gateway.auth import extract_bearer, get_auth
from core.gateway.errors import BodyTooLargeError, openai_error
from core.gateway.scopes import Scope
from core.gateway.streaming import iter_body_with_limit
from core.web.proxy_prefixes import proxy_origin_allowed

logger = logging.getLogger(__name__)
bp = Blueprint("gateway_agentmemory", __name__, url_prefix="/agentmemory")

_R = Scope.MEMORY_READ
_W = Scope.MEMORY_WRITE
_A = Scope.MEMORY_ADMIN


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


async def _proxy(scope: Scope | None) -> tuple[Response, int]:
    if not proxy_origin_allowed(request):
        return openai_error("Forbidden", "forbidden", 403)
    result = None
    if scope is not None:
        auth = get_auth()
        result = auth.check_request(
            bearer=_bearer(),
            remote_addr=request.remote_addr or "",
            allow_loopback_bypass=True,
        )
        if result is None:
            return openai_error("Unauthorized", "invalid_api_key", 401, "authentication_error")
        if not auth.has_scope(result, scope):
            return openai_error(
                "Insufficient scope", "insufficient_scope", 403, param=str(scope)
            )

    path = request.path
    limit = get_body_limit(path)
    if (request.content_length or 0) > limit:
        return openai_error("Body too large", "body_too_large", 413)
    body_iter = request.body
    if not request.content_length:
        raw_body = await request.get_data()
        if len(raw_body) > limit:
            return openai_error("Body too large", "body_too_large", 413)
        if raw_body:
            body_iter = _BytesAsBody(raw_body)

    req_headers = build_request_headers(dict(request.headers), request.remote_addr or "")
    upstream_url = get_upstream_base_url() + path

    t0 = time.monotonic()
    status = 502
    resp_body = b""
    try:
        async with (
            httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=5.0)) as client,
            client.stream(
                request.method,
                upstream_url,
                headers=req_headers,
                content=iter_body_with_limit(body_iter, limit),
                params=request.args,
            ) as upstream,
        ):
            resp_body = await upstream.aread()
            resp_headers = filter_response_headers(dict(upstream.headers))
            status = upstream.status_code
    except BodyTooLargeError:
        return openai_error("Body too large", "body_too_large", 413)
    except httpx.ConnectError:
        return openai_error(
            "agentmemory unavailable", "backend_unavailable", 502, "server_error"
        )

    latency_ms = int((time.monotonic() - t0) * 1000)
    writer = get_writer()
    if writer and result:
        writer.emit(AuditRecord(
            request_id=str(uuid.uuid4()),
            timestamp=datetime.now(UTC),
            client_ip=request.remote_addr or "",
            auth_key_id=result.key_id,
            endpoint=path,
            method=request.method,
            status_code=status,
            latency_ms=latency_ms,
            backend_id="agentmemory",
            request_bytes=request.content_length,
            response_bytes=len(resp_body),
        ))
    return Response(resp_body, status=status, headers=resp_headers)


_ROUTE_TABLE: list[tuple[str, str, Scope | None]] = [
    # === no auth ===
    ("GET",    "/livez",                     None),
    # === memory:read ===
    ("GET",    "/health",                    _R),
    ("GET",    "/config/flags",              _R),
    ("GET",    "/sessions",                  _R),
    ("GET",    "/observations",              _R),
    ("GET",    "/profile",                   _R),
    ("GET",    "/memories",                  _R),
    ("GET",    "/semantic",                  _R),
    ("GET",    "/procedural",                _R),
    ("GET",    "/relations",                 _R),
    ("GET",    "/graph/stats",               _R),
    ("GET",    "/audit",                     _R),
    ("GET",    "/export",                    _R),
    ("GET",    "/snapshots",                 _R),
    ("GET",    "/replay/load",               _R),
    ("GET",    "/replay/sessions",           _R),
    ("GET",    "/team/feed",                 _R),
    ("GET",    "/team/profile",              _R),
    ("GET",    "/slots",                     _R),
    ("GET",    "/slot",                      _R),
    ("GET",    "/frontier",                  _R),
    ("GET",    "/next",                      _R),
    ("GET",    "/actions",                   _R),
    ("GET",    "/actions/get",               _R),
    ("GET",    "/routines",                  _R),
    ("GET",    "/routines/status",           _R),
    ("GET",    "/signals",                   _R),
    ("GET",    "/checkpoints",               _R),
    ("GET",    "/mesh/peers",                _R),
    ("GET",    "/mesh/export",               _R),
    ("GET",    "/branch/detect",             _R),
    ("GET",    "/branch/worktrees",          _R),
    ("GET",    "/branch/sessions",           _R),
    ("GET",    "/sentinels",                 _R),
    ("GET",    "/sketches",                  _R),
    ("GET",    "/crystals",                  _R),
    ("GET",    "/facets",                    _R),
    ("GET",    "/facets/stats",              _R),
    ("GET",    "/lessons",                   _R),
    ("GET",    "/insights",                  _R),
    ("GET",    "/mcp/tools",                 _R),
    ("GET",    "/mcp/resources",             _R),
    ("GET",    "/mcp/prompts",               _R),
    ("POST",   "/search",                    _R),
    ("POST",   "/context",                   _R),
    ("POST",   "/smart-search",              _R),
    ("POST",   "/timeline",                  _R),
    ("POST",   "/graph/query",               _R),
    ("POST",   "/vision-search",             _R),
    ("POST",   "/facets/query",              _R),
    ("POST",   "/lessons/search",            _R),
    ("POST",   "/insights/search",           _R),
    ("POST",   "/actions/edges",             _R),
    ("POST",   "/mcp/resources/read",        _R),
    ("POST",   "/mcp/prompts/get",           _R),
    # === memory:write ===
    ("GET",    "/claude-bridge/read",        _W),
    ("POST",   "/observe",                   _W),
    ("POST",   "/session/start",             _W),
    ("POST",   "/session/end",               _W),
    ("POST",   "/summarize",                 _W),
    ("POST",   "/remember",                  _W),
    ("POST",   "/forget",                    _W),
    ("POST",   "/enrich",                    _W),
    ("POST",   "/consolidate",               _W),
    ("POST",   "/consolidate-pipeline",      _W),
    ("POST",   "/compress-file",             _W),
    ("POST",   "/file-context",              _W),
    ("POST",   "/patterns",                  _W),
    ("POST",   "/generate-rules",            _W),
    ("POST",   "/evict",                     _W),
    ("POST",   "/auto-forget",               _W),
    ("POST",   "/relations",                 _W),
    ("POST",   "/evolve",                    _W),
    ("POST",   "/import",                    _W),
    ("POST",   "/replay/import-jsonl",       _W),
    ("POST",   "/graph/extract",             _W),
    ("POST",   "/team/share",                _W),
    ("POST",   "/claude-bridge/sync",        _W),
    ("POST",   "/snapshot/create",           _W),
    ("POST",   "/vision-embed",              _W),
    ("POST",   "/slot",                      _W),
    ("POST",   "/slot/append",               _W),
    ("POST",   "/slot/replace",              _W),
    ("DELETE", "/slot",                      _W),
    ("POST",   "/slot/reflect",              _W),
    ("POST",   "/actions",                   _W),
    ("POST",   "/actions/update",            _W),
    ("POST",   "/leases/acquire",            _W),
    ("POST",   "/leases/release",            _W),
    ("POST",   "/leases/renew",              _W),
    ("POST",   "/routines",                  _W),
    ("POST",   "/routines/run",              _W),
    ("POST",   "/signals/send",              _W),
    ("POST",   "/checkpoints",               _W),
    ("POST",   "/checkpoints/resolve",       _W),
    ("POST",   "/mesh/peers",                _W),
    ("POST",   "/mesh/sync",                 _W),
    ("POST",   "/mesh/receive",              _W),
    ("POST",   "/flow/compress",             _W),
    ("POST",   "/sentinels",                 _W),
    ("POST",   "/sentinels/trigger",         _W),
    ("POST",   "/sentinels/check",           _W),
    ("POST",   "/sentinels/cancel",          _W),
    ("POST",   "/sketches",                  _W),
    ("POST",   "/sketches/add",              _W),
    ("POST",   "/sketches/promote",          _W),
    ("POST",   "/sketches/discard",          _W),
    ("POST",   "/sketches/gc",               _W),
    ("POST",   "/crystals/create",           _W),
    ("POST",   "/crystals/auto",             _W),
    ("POST",   "/diagnostics",               _W),
    ("POST",   "/diagnostics/heal",          _W),
    ("POST",   "/facets",                    _W),
    ("POST",   "/facets/remove",             _W),
    ("POST",   "/verify",                    _W),
    ("POST",   "/cascade-update",            _W),
    ("POST",   "/lessons",                   _W),
    ("POST",   "/lessons/strengthen",        _W),
    ("POST",   "/obsidian/export",           _W),
    ("POST",   "/reflect",                   _W),
    ("POST",   "/mcp/call",                  _W),
    # === memory:admin ===
    ("POST",   "/migrate",                   _A),
    ("DELETE", "/governance/memories",       _A),
    ("POST",   "/governance/bulk-delete",    _A),
    ("POST",   "/snapshot/restore",          _A),
]


def _build_routes() -> None:
    path_map: dict[str, dict[str, Scope | None]] = defaultdict(dict)
    for method, path, scope in _ROUTE_TABLE:
        path_map[path][method] = scope

    for i, (path, method_scope) in enumerate(path_map.items()):
        methods = list(method_scope.keys())
        frozen = dict(method_scope)

        def make_handler(ms: dict[str, Scope | None]):
            async def handler(**_kwargs: object) -> tuple[Response, int]:
                return await _proxy(ms[request.method])
            return handler

        bp.add_url_rule(
            path,
            endpoint=f"am_{i}",
            view_func=make_handler(frozen),
            methods=methods,
            strict_slashes=False,
        )


@bp.route("/memories/<memory_id>", methods=["GET"], strict_slashes=False)
async def memories_by_id(memory_id: str) -> tuple[Response, int]:
    decoded = unquote(memory_id)
    if decoded in (".", ".."):
        return openai_error("Not found", "not_found", 404)
    return await _proxy(Scope.MEMORY_READ)


_build_routes()


# ---------------------------------------------------------------------------
# Session-authenticated dashboard proxy — Bearer token never reaches browser
# ---------------------------------------------------------------------------

bp_dash = Blueprint("agentmemory_dash", __name__, url_prefix="/api/agentmemory-dash")


_DASH_ALLOW: frozenset[tuple[str, str]] = frozenset({
    ("GET",  "livez"),
    ("GET",  "health"),
    ("GET",  "profile"),
    ("GET",  "sessions"),
    ("GET",  "memories"),
    ("GET",  "audit"),
    ("GET",  "graph/stats"),
    ("POST", "graph/query"),
})


@bp_dash.route("/<path:subpath>", methods=["GET", "POST"], strict_slashes=False)
async def _dash_proxy(subpath: str) -> tuple[Response, int]:
    """Proxy agentmemory requests for the dashboard page.

    Auth: session cookie (PIN) instead of Bearer. The upstream Bearer
    (_upstream_secret) is injected server-side by build_request_headers.
    No credential is ever sent to the browser.
    Only paths in _DASH_ALLOW (all memory:read scope) are permitted.
    """
    if (request.method, subpath.strip("/")) not in _DASH_ALLOW:
        return Response('{"error":"Not allowed"}', status=403,
                        content_type="application/json"), 403

    if current_app.config.get("PIN_AUTH") and not session.get("pin_ok"):
        return Response('{"error":"Unauthorized"}', status=401,
                        content_type="application/json"), 401

    if not proxy_origin_allowed(request):
        return Response('{"error":"Forbidden"}', status=403,
                        content_type="application/json"), 403

    upstream_url = get_upstream_base_url() + "/agentmemory/" + subpath
    limit = get_body_limit("/agentmemory/" + subpath)

    raw_body = await request.get_data()
    if len(raw_body) > limit:
        return Response('{"error":"Body too large"}', status=413,
                        content_type="application/json"), 413

    req_headers = build_request_headers(dict(request.headers), request.remote_addr or "")

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0)) as client:
            resp = await client.request(
                request.method, upstream_url,
                headers=req_headers,
                content=raw_body or None,
                params=request.args,
            )
        resp_headers = filter_response_headers(dict(resp.headers))
        return Response(resp.content, status=resp.status_code, headers=resp_headers), resp.status_code
    except httpx.ConnectError:
        return Response('{"error":"agentmemory unavailable"}', status=502,
                        content_type="application/json"), 502


# ---------------------------------------------------------------------------
# Config API  (GET/PUT /api/gateway/agentmemory/config)
# ---------------------------------------------------------------------------

bp_config = Blueprint("gateway_agentmemory_config", __name__, url_prefix="/api/gateway")

_DEFAULT_BASE_URL = "http://127.0.0.1:3111"


def _session_ok() -> bool:
    if not current_app.config.get("PIN_AUTH"):
        return True
    return bool(session.get("pin_ok"))


@bp_config.route("/agentmemory/config", methods=["GET"])
async def get_agentmemory_config() -> tuple[Response, int]:
    if not _session_ok():
        return Response('{"error":"Unauthorized"}', status=401,
                        content_type="application/json"), 401
    from core.configuration.json_rw import load_config_json
    cfg = load_config_json()
    am_cfg = cfg.get("gateway", {}).get("backends", {}).get("agentmemory", {})
    base_url = am_cfg.get("base_url", _DEFAULT_BASE_URL)
    return Response(json.dumps({"base_url": base_url}),
                    content_type="application/json"), 200


@bp_config.route("/agentmemory/config", methods=["PUT"])
async def put_agentmemory_config() -> tuple[Response, int]:
    if not _session_ok():
        return Response('{"error":"Unauthorized"}', status=401,
                        content_type="application/json"), 401
    body = await request.get_json() or {}
    new_url = (body.get("base_url") or "").strip().rstrip("/")
    try:
        _validate_base_url(new_url)
    except ValueError as exc:
        return Response(json.dumps({"error": str(exc)}), status=400,
                        content_type="application/json"), 400
    from core.configuration.json_rw import load_config_json, save_config_json
    from core.settings_core.secret_store import decrypt
    cfg = load_config_json()
    am_cfg = cfg.setdefault("gateway", {}).setdefault("backends", {}).setdefault("agentmemory", {})
    am_cfg["base_url"] = new_url
    save_config_json(cfg)
    secret_enc = am_cfg.get("secret_enc")
    secret = decrypt(secret_enc) if secret_enc else None
    _configure_proxy(new_url, secret)
    return Response(json.dumps({"base_url": new_url}),
                    content_type="application/json"), 200
