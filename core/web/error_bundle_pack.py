"""Bundle minimization and URL packing helpers."""

from __future__ import annotations

import base64
import copy
import json
import urllib.parse
import zlib
from typing import Any

from quart import request

from core.search_api.server_info import APP_VERSION
from core.web.error_bundle_shared import (
    _QR_CHAR_BUDGET,
    _truncate_text,
    _urlsafe_b64_nopad,
)


def encode_error_bundle_gzip_base64(bundle: dict[str, Any]) -> str:
    raw = json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    gz = zlib.compress(raw, level=9, wbits=16 + zlib.MAX_WBITS)
    return base64.b64encode(gz).decode("ascii")


def _set_compact_logs(bundle: dict[str, Any], *, limit: int, width: int) -> None:
    logs = list(bundle.get("artifacts", {}).get("recent_logs", []) or [])
    bundle.setdefault("artifacts", {})["recent_logs"] = [_truncate_text(str(line), width) for line in logs[-limit:]]


def _trim_extensions(bundle: dict[str, Any], limit: int) -> None:
    items = list(bundle.get("state", {}).get("extensions", []) or [])
    bundle.setdefault("state", {})["extensions"] = items[:limit]


def _trim_traceback(bundle: dict[str, Any], limit: int) -> None:
    err = bundle.setdefault("error", {})
    trace = str(err.get("traceback", "") or "")
    err["traceback"] = trace[-limit:]


def _trim_request_body(bundle: dict[str, Any], limit: int) -> None:
    req = bundle.setdefault("request", {})
    body = req.get("body_preview")
    if isinstance(body, str):
        req["body_preview"] = _truncate_text(body, limit)


def _minimize_server_info(bundle: dict[str, Any]) -> None:
    state = bundle.setdefault("state", {})
    server_info = state.get("server_info")
    if isinstance(server_info, dict):
        state["server_info"] = {
            "boot_state": server_info.get("boot_state"),
            "server_mode": server_info.get("server_mode"),
            "active_ui": server_info.get("active_ui"),
            "active_profile": server_info.get("active_profile"),
        }


def _minimal_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": bundle.get("schema"),
        "error_id": bundle.get("error_id"),
        "captured_at": bundle.get("captured_at"),
        "app": bundle.get("app"),
        "request": {
            "request_id": bundle.get("request", {}).get("request_id"),
            "method": bundle.get("request", {}).get("method"),
            "path": bundle.get("request", {}).get("path"),
            "query": bundle.get("request", {}).get("query"),
        },
        "error": {
            "class": bundle.get("error", {}).get("class"),
            "message": bundle.get("error", {}).get("message"),
            "status_code": bundle.get("error", {}).get("status_code"),
            "traceback": bundle.get("error", {}).get("traceback"),
            "frames": bundle.get("error", {}).get("frames"),
        },
        "state": {"server_info": bundle.get("state", {}).get("server_info")},
        "artifacts": {"recent_logs": bundle.get("artifacts", {}).get("recent_logs")},
        "privacy": bundle.get("privacy"),
    }


def _stub_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": bundle.get("schema"),
        "error_id": bundle.get("error_id"),
        "captured_at": bundle.get("captured_at"),
        "app": {"version": bundle.get("app", {}).get("version")},
        "request": {
            "request_id": bundle.get("request", {}).get("request_id"),
            "method": bundle.get("request", {}).get("method"),
            "path": bundle.get("request", {}).get("path"),
        },
        "error": {
            "class": bundle.get("error", {}).get("class"),
            "message": bundle.get("error", {}).get("message"),
            "status_code": bundle.get("error", {}).get("status_code"),
            "traceback": str(bundle.get("error", {}).get("traceback", "") or "")[-280:],
        },
    }


def _encoded_bundle_text(bundle: dict[str, Any]) -> str:
    raw = json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    gz = zlib.compress(raw, level=9, wbits=16 + zlib.MAX_WBITS)
    return _urlsafe_b64_nopad(gz)


def pack_error_bundle(bundle: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    working = copy.deepcopy(bundle)
    mutators = [
        lambda b: _set_compact_logs(b, limit=10, width=160),
        lambda b: _trim_traceback(b, 1400),
        lambda b: _trim_request_body(b, 320),
        lambda b: _trim_extensions(b, 10),
        lambda b: _set_compact_logs(b, limit=5, width=120),
        lambda b: _minimize_server_info(b),
        lambda b: _trim_traceback(b, 900),
        lambda b: b.setdefault("artifacts", {}).update({"recent_logs": []}),
        lambda b: _trim_request_body(b, 120),
        lambda b: _trim_traceback(b, 500),
    ]
    encoded = _encoded_bundle_text(working)
    for mutate in mutators:
        if len(encoded) + 240 <= _QR_CHAR_BUDGET:
            return encoded, working
        mutate(working)
        encoded = _encoded_bundle_text(working)
    if len(encoded) + 240 <= _QR_CHAR_BUDGET:
        return encoded, working
    minimal = _minimal_bundle(working)
    encoded = _encoded_bundle_text(minimal)
    if len(encoded) + 240 <= _QR_CHAR_BUDGET:
        return encoded, minimal
    stub = _stub_bundle(minimal)
    return _encoded_bundle_text(stub), stub


def build_bug_report_url(bundle: dict[str, Any], base_url: str) -> tuple[str, dict[str, Any]]:
    encoded, packed_bundle = pack_error_bundle(bundle)
    exc_label = f"{packed_bundle.get('error', {}).get('class', 'Error')}: {packed_bundle.get('error', {}).get('message', '')}"
    query = {
        "v": packed_bundle.get("app", {}).get("version", APP_VERSION),
        "p": packed_bundle.get("request", {}).get("path", request.path[:80]),
        "e": _truncate_text(exc_label, 120),
        "d": encoded,
    }
    return f"{base_url}?{urllib.parse.urlencode(query)}", packed_bundle
