"""Capture and enrich structured error bundles from request context."""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import os
import platform
import sys
import traceback as tb_module
from pathlib import Path
from typing import Any

from quart import current_app, g, request, session

from core.extensions_core.lifecycle.runtime import get_extension_manager
from core.infra_core.log_ring_buffer import log_ring
from core.search_api.server_info import APP_VERSION, build_server_info_response
from core.services_core.app_runtime_state import get_config
from core.services_core.db_api import (
    get_db_path,
    get_start_time,
    get_startup_migration_info,
    get_startup_status,
    is_boot_ready,
)
from core.web.api_rate_limit import get_client_ip
from core.web.auth_restart import is_local_request
from core.web.error_bundle_shared import (
    _ERROR_BUNDLE_SCHEMA,
    _SECRET_KEY_RE,
    _build_privacy_rules,
    _ensure_error_id,
    _normalize_path_text,
    _sanitize_for_json,
    _truncate_text,
)
from core.web.public_host import resolve_public_host


def _get_request_headers_summary() -> dict[str, str]:
    headers = {}
    user_agent = request.headers.get("User-Agent", "")
    referer = request.headers.get("Referer", "") or request.referrer or ""
    if user_agent:
        headers["user_agent"] = _truncate_text(user_agent, 200)
    if referer:
        headers["referer"] = _truncate_text(_normalize_path_text(referer), 200)
    return headers


async def _get_request_body_preview() -> Any:
    try:
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            return None
        if request.is_json:
            payload = await request.get_json(silent=True)
            if payload is None:
                return None
            text = json.dumps(_sanitize_for_json(payload), ensure_ascii=False, separators=(",", ":"))
            return _truncate_text(text, 600)
        raw = await request.get_data(cache=True, as_text=True)
        raw = (raw or "").strip()
        if not raw:
            return None
        return _truncate_text(_normalize_path_text(raw), 600)
    except Exception as exc:
        return f"<unavailable: {type(exc).__name__}>"


def _get_extensions_summary() -> list[dict[str, Any]]:
    try:
        mgr = get_extension_manager()
        items = mgr.list_extensions()
    except Exception as exc:
        return [{"capture_error": type(exc).__name__}]
    return [{
        "name": item.get("name"),
        "version": item.get("version"),
        "enabled": item.get("enabled"),
        "status": item.get("status"),
        "type": item.get("type"),
    } for item in items]


def _get_server_info_summary() -> dict[str, Any]:
    try:
        config = current_app.config
        sess = dict(session)
        local_only_ok = is_local_request()
        host = resolve_public_host(get_client_ip())
        info = build_server_info_response(config, sess, local_only_ok, host)
        return {
            "boot_state": info.get("boot_state"),
            "server_mode": info.get("server_mode"),
            "version": info.get("version"),
            "active_profile": info.get("active_profile"),
            "db_path": _normalize_path_text(str(info.get("db_path", ""))) if info.get("db_path") else None,
            "db_size_mb": info.get("db_size_mb"),
            "file_count": info.get("file_count"),
            "tag_count": info.get("tag_count"),
            "schema_version": info.get("schema_version"),
            "active_ui": info.get("active_ui"),
            "startup_status": info.get("startup_status"),
            "startup_migration": info.get("startup_migration"),
            "restart_available_now": info.get("restart_available_now"),
            "restart_blockers": info.get("restart_blockers"),
        }
    except Exception as exc:
        return {"capture_error": type(exc).__name__}


def _get_recent_logs() -> list[str]:
    entries = log_ring.recent(limit=25)
    lines: list[str] = []
    for entry in entries:
        ts = dt.datetime.fromtimestamp(entry.get("timestamp", 0), tz=dt.UTC).isoformat(timespec="seconds")
        level = entry.get("level", "")
        source = entry.get("source", "")
        message = _truncate_text(_normalize_path_text(entry.get("message", "")), 220)
        lines.append(f"{ts} [{level}] {source} {message}".strip())
    return lines


def _get_error_frames(exc: Exception) -> list[dict[str, Any]]:
    frames = []
    for frame in tb_module.extract_tb(exc.__traceback__)[-8:]:
        frames.append({
            "file": _normalize_path_text(frame.filename),
            "line": frame.lineno,
            "function": frame.name,
            "code": _truncate_text(frame.line or "", 200),
        })
    return frames


def _build_capture_mode() -> str:
    return "api" if request.path.startswith("/api/") else "page"


async def build_error_bundle(exc: Exception) -> dict[str, Any]:
    query = {k: "***" if _SECRET_KEY_RE.search(k) else _sanitize_for_json(v) for k, v in request.args.items()}
    body_preview = await _get_request_body_preview()
    trace_text = "".join(tb_module.format_exception(type(exc), exc, exc.__traceback__))
    error_id_seed = f"{type(exc).__name__}|{request.method}|{request.path}|{trace_text[-256:]}"
    # Groups identical reports together; not a security primitive. sha256 rather
    # than sha1 so the shared semgrep rule stays satisfied without a suppression.
    error_id = "err_" + hashlib.sha256(
        error_id_seed.encode("utf-8", errors="replace"), usedforsecurity=False
    ).hexdigest()[:12]
    bundle = {
        "schema": _ERROR_BUNDLE_SCHEMA,
        "error_id": error_id,
        "captured_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "capture_mode": _build_capture_mode(),
        "app": {
            "name": "YU AI Manager",
            "version": APP_VERSION,
            "ui": current_app.config.get("ACTIVE_UI") or get_config().get("ui") or "default",
            "mode": current_app.config.get("SERVER_MODE", "full"),
        },
        "runtime": {
            "os": {"platform": platform.system(), "release": platform.release(), "arch": platform.machine()},
            "python": sys.version.split()[0],
            "pid": os.getpid(),
            "cwd": _normalize_path_text(str(Path.cwd())),
            "uptime_sec": int(dt.datetime.now(tz=dt.UTC).timestamp() - get_start_time()),
            "boot_ready": is_boot_ready(),
        },
        "request": {
            "kind": "http",
            "request_id": str(getattr(g, "request_id", "") or ""),
            "method": request.method,
            "path": request.path,
            "query": query,
            "body_preview": body_preview,
            "headers": _get_request_headers_summary(),
            "remote_addr": request.remote_addr or "",
            "endpoint": request.endpoint or "",
        },
        "error": {
            "class": type(exc).__name__,
            "message": str(exc),
            "status_code": 500,
            "traceback": _normalize_path_text(trace_text[-1800:]),
            "frames": _get_error_frames(exc),
        },
        "inputs": {"ui_action": request.headers.get("X-YU-Action", ""), "referer": _normalize_path_text(request.referrer or "")},
        "state": {
            "server_info": _get_server_info_summary(),
            "extensions": _get_extensions_summary(),
            "db": {
                "db_path": _normalize_path_text(str(get_db_path())),
                "startup_status": get_startup_status(),
                "startup_migration": get_startup_migration_info(),
            },
        },
        "repro": {
            "ui_events": [{"ts": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), "type": "request", "target": f"{request.method} {request.path}"}],
            "user_note": "",
        },
        "artifacts": {"recent_logs": _get_recent_logs()},
        "privacy": {"redacted": True, "rules": _build_privacy_rules()},
    }
    return _sanitize_for_json(bundle)


def enrich_error_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    safe = _sanitize_for_json(copy.deepcopy(bundle if isinstance(bundle, dict) else {}))
    if not isinstance(safe, dict):
        safe = {}
    safe["error_id"] = _ensure_error_id(safe)
    safe.setdefault("captured_at", dt.datetime.now(dt.UTC).isoformat(timespec="seconds"))
    safe.setdefault("schema", "yu://client-error-bundle/1")
    app = safe.setdefault("app", {})
    if isinstance(app, dict):
        app.setdefault("name", "YU AI Manager")
        app.setdefault("version", APP_VERSION)
        app.setdefault("ui", current_app.config.get("ACTIVE_UI") or get_config().get("ui") or "default")
        app.setdefault("mode", current_app.config.get("SERVER_MODE", "full"))
    runtime = safe.setdefault("runtime", {})
    if isinstance(runtime, dict):
        runtime.setdefault("os", {"platform": platform.system(), "release": platform.release(), "arch": platform.machine()})
        runtime.setdefault("python", sys.version.split()[0])
        runtime.setdefault("pid", os.getpid())
        runtime.setdefault("cwd", _normalize_path_text(str(Path.cwd())))
        runtime.setdefault("uptime_sec", int(dt.datetime.now(tz=dt.UTC).timestamp() - get_start_time()))
    state = safe.setdefault("state", {})
    if isinstance(state, dict):
        state["server_info"] = _get_server_info_summary()
        state["extensions"] = _get_extensions_summary()
        state.setdefault("db", {
            "db_path": _normalize_path_text(str(get_db_path())),
            "startup_status": get_startup_status(),
            "startup_migration": get_startup_migration_info(),
        })
    artifacts = safe.setdefault("artifacts", {})
    if isinstance(artifacts, dict):
        artifacts["recent_logs"] = _get_recent_logs()
    privacy = safe.setdefault("privacy", {})
    if isinstance(privacy, dict):
        privacy["redacted"] = True
        privacy["rules"] = _build_privacy_rules()
    return _sanitize_for_json(safe)
