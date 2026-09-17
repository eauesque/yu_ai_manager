from __future__ import annotations

import asyncio
import json
import logging as _logging
import re as _re
import uuid
import uuid as _uuid_mod
from typing import Any
from urllib.parse import urlparse as _urlparse

from quart import Blueprint, Response, current_app, jsonify, request

from core.gateway.errors import openai_error
from core.infra_core.api_errors import api_error
from core.infra_core.api_request import require_json_dict
from core.web.auth_helpers import check_mutation_auth

bp = Blueprint("gateway_backends", __name__, url_prefix="/api/gateway")

_VALID_TYPES = frozenset({"sd_webui", "comfyui", "ollama", "gradio"})
_HOST = "127.0.0.1"
_logger = _logging.getLogger(__name__)

# In-memory store (populated from config.json on startup)
_backends: dict[str, dict[str, Any]] = {}


def _load_from_config() -> None:
    try:
        from core.configuration.json_rw import load_config_json

        cfg = load_config_json()
        gateway_cfg = cfg.get("gateway", {})
        raw = gateway_cfg.get("backends", {})
        _backends.clear()
        for bid, value in raw.items():
            if not isinstance(value, dict) or not value.get("base_url") or not value.get("type"):
                continue
            entry = {
                "type": value["type"],
                "base_url": value["base_url"].rstrip("/"),
                "name": value.get("name", ""),
                "color": value.get("color", ""),
            }
            port = _extract_port(entry["base_url"])
            if port is not None:
                entry["port"] = port
            from core.gateway import backend_registry as _reg

            _reg.apply_backend_defaults(entry)
            _backends[bid] = entry
        from core.gateway import backend_registry as _reg

        defaults_cfg = gateway_cfg.get("defaults", {})
        _reg.load_state(
            backends=dict(_backends),
            defaults={
                "default_comfy_backend_id": defaults_cfg.get(
                    "default_comfy_backend_id",
                    gateway_cfg.get("default_comfy_backend_id"),
                ),
                "default_sd_backend_id": defaults_cfg.get(
                    "default_sd_backend_id",
                    gateway_cfg.get("default_sd_backend_id"),
                ),
            },
            groups=gateway_cfg.get("groups", {}),
        )
    except Exception as exc:
        _logger.warning("[gateway:backends] load from config failed: %s", exc)


def _get_state(bid: str) -> str:
    probe = current_app.extensions.get("gateway_probe")
    if probe is None:
        return "unknown"
    return str(probe.get_state(bid))


def _port_in_use(port: int, exclude_id: str | None = None) -> bool:
    return any(value["port"] == port for bid, value in _backends.items() if bid != exclude_id)


def _extract_port(base_url: str) -> int | None:
    try:
        return _urlparse(base_url).port
    except ValueError:
        return None


def _validate_base_url(url: str) -> str | None:
    """Return error message or None if valid."""
    try:
        p = _urlparse(url.rstrip("/"))
        port = p.port
    except ValueError as exc:
        return str(exc)
    if p.scheme not in ("http", "https"):
        return "scheme must be http or https"
    if not p.hostname:
        return "hostname required"
    if p.username or p.password:
        return "userinfo not allowed"
    if p.path and p.path != "/":
        return "path not allowed"
    if p.query or p.fragment:
        return "query/fragment not allowed"
    if "\\" in url:
        return "backslash not allowed"
    if port is not None and not (1 <= port <= 65535):
        return "port out of range"
    return None


def _is_valid_color(c: str) -> bool:
    return bool(_re.fullmatch(r"#[0-9a-fA-F]{6}", c))


def _normalize_backend_input(data: dict) -> tuple[dict | None, str | None]:
    """Accept {type, base_url} or legacy {type, port}. Returns (entry, error)."""
    from core.gateway import backend_registry as _reg

    raw_type = data.get("type")
    btype = raw_type.strip() if isinstance(raw_type, str) else ""
    if not btype:
        return None, "type required"
    if btype not in _VALID_TYPES:
        return None, "type must be one of sd_webui, comfyui, ollama, gradio"
    raw_base_url = data.get("base_url")
    base_url = raw_base_url.strip() if isinstance(raw_base_url, str) else ""
    if not base_url:
        port = data.get("port")
        if port is None:
            return None, "base_url or port required"
        if not isinstance(port, int) or not (1 <= port <= 65535):
            return None, "port must be 1-65535"
        base_url = f"http://127.0.0.1:{port}"
    base_url = base_url.rstrip("/")
    err = _validate_base_url(base_url)
    if err:
        return None, f"base_url: {err}"
    raw_name = data.get("name")
    raw_color = data.get("color")
    name = raw_name.strip() if isinstance(raw_name, str) else ""
    color = raw_color.strip() if isinstance(raw_color, str) else ""
    if color and not _is_valid_color(color):
        return None, "color must be #rrggbb"
    if name and len(name) > 100:
        return None, "name max 100 chars"
    entry: dict = {"type": btype, "base_url": base_url, "name": name, "color": color}
    port = _extract_port(base_url)
    if port is not None:
        entry["port"] = port
    _reg.apply_backend_defaults(entry)
    return entry, None


def _mirror_registry_state() -> None:
    from core.gateway import backend_registry as _reg

    _backends.clear()
    for entry in _reg.list_backends():
        bid = entry.pop("id")
        _backends[bid] = entry


def _backend_response(backend_id: str, entry: dict[str, Any]) -> dict[str, Any]:
    from core.gateway import backend_registry as _reg

    item = dict(entry)
    _reg.apply_backend_defaults(item)
    item["id"] = backend_id
    item["status"] = _get_state(backend_id)
    item["port"] = _extract_port(item["base_url"])
    return item


def _delete_backend_cascade(backend_id: str) -> None:
    """Must be called inside mutate_and_save fn()."""
    from core.gateway.backend_registry import (
        _backends,
        _defaults,
        _groups,
        fire_invalidation,
    )

    for key in ("default_comfy_backend_id", "default_sd_backend_id"):
        if _defaults.get(key) == backend_id:
            _defaults[key] = None
    for grp in _groups.values():
        if backend_id in grp.get("backend_ids", []):
            grp["backend_ids"] = [b for b in grp["backend_ids"] if b != backend_id]
    del _backends[backend_id]
    fire_invalidation(backend_id, "deleted")


@bp.before_app_serving
async def _init() -> None:
    _load_from_config()
    probe = current_app.extensions.get("gateway_probe")
    if probe is not None:
        from core.gateway import backend_registry as _reg

        _reg.set_probe(probe)


@bp.route("/backends", methods=["GET"])
async def list_backends():
    from core.gateway import backend_registry as _reg

    return Response(
        json.dumps(
            {"backends": [_backend_response(value["id"], value) for value in _reg.list_backends()]},
            ensure_ascii=False,
        ),
        content_type="application/json",
    )


@bp.route("/backends", methods=["POST"])
async def add_backend():
    from core.gateway import backend_registry as _reg

    err = await check_mutation_auth(request)
    if err:
        return err
    body = await request.get_json() or {}
    entry, input_err = _normalize_backend_input(body)
    if input_err:
        return openai_error(input_err, "invalid_request_error", 422)
    assert entry is not None
    bid = str(uuid.uuid4())

    def _add():
        from core.gateway.backend_registry import _backends

        _backends[bid] = dict(entry)

    await _reg.mutate_and_save(_add)
    _mirror_registry_state()
    return Response(
        json.dumps(
            _backend_response(bid, entry),
            ensure_ascii=False,
        ),
        content_type="application/json",
    )


@bp.route("/backends/<backend_id>", methods=["PATCH"])
async def patch_backend(backend_id: str):
    from core.gateway import backend_registry as _reg
    from core.gateway.backend_registry import fire_invalidation

    err = await check_mutation_auth(request)
    if err:
        return err
    current = _reg.get_backend(backend_id)
    if current is None:
        return openai_error("backend not found", "not_found", 404)
    body = await request.get_json() or {}
    entry = dict(current)
    if "type" in body:
        btype = body["type"].strip() if isinstance(body["type"], str) else ""
        if btype not in _VALID_TYPES:
            return openai_error(
                "type must be one of sd_webui, comfyui, ollama, gradio",
                "invalid_request_error",
                422,
            )
        entry["type"] = btype
    if "base_url" in body:
        raw_base_url = body.get("base_url")
        base_url = raw_base_url.strip().rstrip("/") if isinstance(raw_base_url, str) else ""
        err_msg = _validate_base_url(base_url)
        if err_msg:
            return openai_error(f"base_url: {err_msg}", "invalid_request_error", 422)
        entry["base_url"] = base_url
        port = _extract_port(base_url)
        if port is not None:
            entry["port"] = port
    if "port" in body:
        port = body["port"]
        if not isinstance(port, int) or not (1 <= port <= 65535):
            return openai_error("port must be 1-65535", "invalid_request_error", 422)
        entry["port"] = port
        entry["base_url"] = f"http://{_HOST}:{port}"
    if "name" in body:
        raw_name = body.get("name")
        name = raw_name.strip() if isinstance(raw_name, str) else ""
        if len(name) > 100:
            return openai_error("name max 100 chars", "invalid_request_error", 422)
        entry["name"] = name
    if "color" in body:
        raw_color = body.get("color")
        color = raw_color.strip() if isinstance(raw_color, str) else ""
        if color and not _is_valid_color(color):
            return openai_error("color must be #rrggbb", "invalid_request_error", 422)
        entry["color"] = color
    from core.gateway import backend_registry as _reg_defaults

    _reg_defaults.apply_backend_defaults(entry)

    def _patch():
        from core.gateway.backend_registry import _backends

        old = _backends[backend_id]
        type_changed = old.get("type") != entry.get("type")
        base_url_changed = old.get("base_url") != entry.get("base_url")
        _backends[backend_id] = dict(entry)
        if type_changed:
            fire_invalidation(backend_id, "type_changed")
        if base_url_changed:
            fire_invalidation(backend_id, "base_url_changed")

    await _reg.mutate_and_save(_patch)
    _mirror_registry_state()
    return Response(
        json.dumps(
            _backend_response(backend_id, entry),
            ensure_ascii=False,
        ),
        content_type="application/json",
    )


@bp.route("/backends/<backend_id>", methods=["DELETE"])
async def delete_backend(backend_id: str):
    from core.gateway import backend_registry as _reg

    err = await check_mutation_auth(request)
    if err:
        return err
    if _reg.get_backend(backend_id) is None:
        return openai_error("backend not found", "not_found", 404)
    await _reg.mutate_and_save(lambda: _delete_backend_cascade(backend_id))
    _mirror_registry_state()
    return Response(json.dumps({"deleted": backend_id}), content_type="application/json")


@bp.route("/local/status", methods=["GET"])
async def local_status():
    from core.gateway import backend_registry as _reg

    return Response(
        json.dumps(
            {
                "backends": [
                    {
                        "id": value["id"],
                        "type": value["type"],
                        "base_url": value["base_url"],
                        "state": _get_state(value["id"]),
                    }
                    for value in _reg.list_backends()
                ]
            },
            ensure_ascii=False,
        ),
        content_type="application/json",
    )


@bp.route("/groups", methods=["GET"])
async def list_groups_route():
    from core.gateway import backend_registry as _reg

    return jsonify(_reg.list_groups())


@bp.route("/groups", methods=["POST"])
async def create_group_route():
    from core.gateway import backend_registry as _reg

    err = await check_mutation_auth(request)
    if err:
        return err
    data, verr = await require_json_dict(request)
    if verr:
        return api_error(verr[0]["error"], verr[1])
    assert data is not None
    name = (data.get("name") or "").strip()
    if not name:
        return api_error("name required", 400)
    if len(name) > 100:
        return api_error("name max 100 chars", 400)
    existing_groups = _reg.list_groups()
    if any(g["name"] == name for g in existing_groups):
        return api_error(f"group name '{name}' already exists", 409)
    raw_bids = data.get("backend_ids") or []
    if not isinstance(raw_bids, list):
        return api_error("backend_ids must be a list", 400)
    for item in raw_bids:
        if not isinstance(item, str):
            return api_error("backend_ids items must be strings", 400)
    bids = list(dict.fromkeys(raw_bids))
    current_backends = {e["id"] for e in _reg.list_backends()}
    for bid in bids:
        if bid not in current_backends:
            return api_error(f"backend {bid} not found", 400)
    if len(bids) > 16:
        return api_error("backend_ids max 16", 400)
    gid = str(_uuid_mod.uuid4())

    def _create():
        from core.gateway.backend_registry import _groups

        _groups[gid] = {"name": name, "backend_ids": bids}

    await _reg.mutate_and_save(_create)
    return jsonify({"id": gid, "name": name, "backend_ids": bids}), 201


@bp.route("/groups/<group_id>", methods=["PATCH"])
async def patch_group_route(group_id: str):
    from core.gateway import backend_registry as _reg

    err = await check_mutation_auth(request)
    if err:
        return err
    if not _reg.get_group(group_id):
        return api_error("group not found", 404)
    data, verr = await require_json_dict(request)
    if verr:
        return api_error(verr[0]["error"], verr[1])
    assert data is not None

    def _patch():
        from core.gateway.backend_registry import _backends, _groups

        grp = _groups[group_id]
        if "name" in data:
            nm = (data["name"] or "").strip()
            if not nm:
                raise ValueError("name required")
            if len(nm) > 100:
                raise ValueError("name max 100 chars")
            if any(gid != group_id and g["name"] == nm for gid, g in _groups.items()):
                raise ValueError(f"group name '{nm}' already exists")
            grp["name"] = nm
        if "backend_ids" in data:
            raw_bids = data["backend_ids"] or []
            if not isinstance(raw_bids, list):
                raise ValueError("backend_ids must be a list")
            for item in raw_bids:
                if not isinstance(item, str):
                    raise ValueError("backend_ids items must be strings")
            bids = list(dict.fromkeys(raw_bids))
            for bid in bids:
                if bid not in _backends:
                    raise ValueError(f"backend {bid} not found")
            if len(bids) > 16:
                raise ValueError("backend_ids max 16")
            grp["backend_ids"] = bids

    try:
        await _reg.mutate_and_save(_patch)
    except ValueError as exc:
        code = 409 if "already exists" in str(exc) else 400
        return api_error(str(exc), code)
    return jsonify(_reg.get_group(group_id))


@bp.route("/groups/<group_id>", methods=["DELETE"])
async def delete_group_route(group_id: str):
    from core.gateway import backend_registry as _reg

    err = await check_mutation_auth(request)
    if err:
        return err
    if not _reg.get_group(group_id):
        return api_error("group not found", 404)

    def _delete():
        from core.gateway.backend_registry import _groups

        _groups.pop(group_id, None)

    await _reg.mutate_and_save(_delete)
    return "", 204


@bp.route("/defaults", methods=["GET"])
async def get_defaults_route():
    from core.gateway import backend_registry as _reg

    return jsonify(_reg.get_defaults())


@bp.route("/defaults", methods=["PATCH"])
async def patch_defaults_route():
    from core.gateway import backend_registry as _reg

    err = await check_mutation_auth(request)
    if err:
        return err
    data, verr = await require_json_dict(request)
    if verr:
        return api_error(verr[0]["error"], verr[1])
    assert data is not None

    def _patch():
        from core.gateway.backend_registry import _backends, _defaults

        for key in ("default_comfy_backend_id", "default_sd_backend_id"):
            if key not in data:
                continue
            val = data[key]
            if val is None:
                _defaults[key] = None
                continue
            e = _backends.get(val)
            if not e:
                raise ValueError(f"{key}: backend {val} not found")
            expected = "comfyui" if "comfy" in key else "sd_webui"
            if e.get("type") != expected:
                raise ValueError(f"{key}: type mismatch (expected {expected})")
            _defaults[key] = val

    try:
        await _reg.mutate_and_save(_patch)
    except ValueError as exc:
        return api_error(str(exc), 400)
    return jsonify(_reg.get_defaults())


# ---------------------------------------------------------------------------
# Scan routes
# ---------------------------------------------------------------------------

import time as _time

from core.gateway.scan import ScanRegistry as _ScanRegistry

_scan_registry: _ScanRegistry | None = None


def _get_registry() -> _ScanRegistry:
    global _scan_registry
    reg = current_app.extensions.get("gateway_scan_registry")
    if reg is not None:
        return reg
    if _scan_registry is None:
        _scan_registry = _ScanRegistry()
    return _scan_registry


@bp.route("/backends/scan", methods=["POST"])
async def start_scan():
    err = await check_mutation_auth(request)
    if err:
        return err

    body = await request.get_json() or {}
    include_defaults = bool(body.get("include_defaults", True))
    range_ = body.get("range")
    full_scan = bool(body.get("full_scan", False))
    auto_register = bool(body.get("auto_register", False))

    if full_scan and range_:
        return openai_error("full_scan と range は同時指定不可", "invalid_request_error", 422)
    if not (include_defaults or range_ or full_scan):
        return openai_error("スキャン対象がありません", "invalid_request_error", 422)
    if range_:
        mn, mx = range_.get("min", 0), range_.get("max", 0)
        if not (isinstance(mn, int) and isinstance(mx, int) and 1 <= mn <= 65535 and 1 <= mx <= 65535 and mn <= mx):
            return openai_error("range が不正です", "invalid_request_error", 422)

    params: dict[str, Any] = {
        "include_defaults": include_defaults,
        "full_scan": full_scan,
        "auto_register": auto_register,
    }
    if range_:
        params["range"] = range_

    if auto_register:

        async def _register_cb(btype: str, port: int, base_url: str):
            from core.gateway import backend_registry as _reg

            normalized = base_url.rstrip("/")
            for entry in _reg.list_backends():
                if entry.get("type") == btype and entry.get("base_url") == normalized:
                    return False, True
            bid_new = str(uuid.uuid4())
            entry: dict[str, Any] = {
                "type": btype,
                "port": port,
                "base_url": normalized,
            }
            _reg.apply_backend_defaults(entry)

            def _add():
                from core.gateway.backend_registry import _backends

                _backends[bid_new] = entry

            await _reg.mutate_and_save(_add)
            _mirror_registry_state()
            return True, False

        params["_register_cb"] = _register_cb

    try:
        job = await _get_registry().start_scan(params)
    except ValueError:
        return openai_error("スキャンが既に実行中です", "conflict", 409)

    return Response(json.dumps({"scanId": job.scan_id}), content_type="application/json")


@bp.route("/backends/scan/<scan_id>/stream", methods=["GET"])
async def scan_stream(scan_id: str):
    job = _get_registry().get_job(scan_id)
    if job is None:
        return openai_error("scan job not found", "not_found", 404)

    async def generate():
        for event in job.get_buffered():
            yield f"data: {json.dumps(event)}\n\n"
        if job.state != "running":
            return
        q: asyncio.Queue = asyncio.Queue()
        job.subscribe(q)
        try:
            last_ka = _time.monotonic()
            while True:
                timeout = 30.0 - (_time.monotonic() - last_ka)
                try:
                    event = await asyncio.wait_for(q.get(), timeout=max(timeout, 0.05))
                    yield f"data: {json.dumps(event)}\n\n"
                    if event["type"] in ("done", "cancelled"):
                        break
                except TimeoutError:
                    yield ": keepalive\n\n"
                    last_ka = _time.monotonic()
        finally:
            job.unsubscribe(q)

    return Response(
        generate(),
        content_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@bp.route("/backends/scan/<scan_id>", methods=["DELETE"])
async def cancel_scan(scan_id: str):
    err = await check_mutation_auth(request)
    if err:
        return err

    cancelled = await _get_registry().cancel_scan(scan_id)
    if not cancelled:
        return openai_error("scan job not found or not running", "not_found", 404)
    return Response(json.dumps({"cancelled": True}), content_type="application/json")
