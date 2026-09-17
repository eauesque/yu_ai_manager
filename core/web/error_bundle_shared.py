"""Shared helpers for structured error bundles."""

from __future__ import annotations

import base64
import hashlib
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_ERROR_BUNDLE_SCHEMA = "yu://error-bundle/1"
_QR_CHAR_BUDGET = 2953
_SECRET_KEY_RE = re.compile(r"(token|secret|password|passwd|authorization|cookie|key|session)", re.IGNORECASE)


def _urlsafe_b64_nopad(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _normalize_path_text(value: str) -> str:
    if not value:
        return value
    text = value
    try:
        home = str(Path.home())
        text = text.replace(home, "<home>")
    except Exception:
        logger.warning("web startup step failed", exc_info=True)
    text = re.sub(r"([A-Za-z]:\\Users\\)[^\\]+", r"\1<user>", text)
    text = re.sub(r"(/Users/)[^/]+", r"\1<user>", text)
    return text


def _truncate_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)] + "..."


def _sanitize_for_json(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _normalize_path_text(value)
    if isinstance(value, (list, tuple)):
        return [_sanitize_for_json(v) for v in value]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, val in value.items():
            if _SECRET_KEY_RE.search(str(key)):
                out[str(key)] = "***"
            else:
                out[str(key)] = _sanitize_for_json(val)
        return out
    return _normalize_path_text(str(value))


def _build_privacy_rules() -> list[str]:
    return [
        "authorization-like fields masked",
        "cookie-like fields masked",
        "token-like fields masked",
        "user home paths normalized",
    ]


def _ensure_error_id(bundle: dict[str, Any]) -> str:
    existing = str(bundle.get("error_id") or "").strip()
    if existing:
        return existing
    req = bundle.get("request", {}) if isinstance(bundle.get("request"), dict) else {}
    err = bundle.get("error", {}) if isinstance(bundle.get("error"), dict) else {}
    seed = "|".join([
        str(bundle.get("schema") or ""),
        str(req.get("method") or ""),
        str(req.get("path") or ""),
        str(err.get("message") or ""),
        str(err.get("stack") or err.get("traceback") or ""),
    ])
    # Groups identical reports together; not a security primitive. sha256 rather
    # than sha1 so the shared semgrep rule stays satisfied without a suppression.
    return "err_" + hashlib.sha256(
        seed.encode("utf-8", errors="replace"), usedforsecurity=False
    ).hexdigest()[:12]
