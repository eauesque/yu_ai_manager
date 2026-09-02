"""Bitwarden CLI helpers: availability check, session handling, status, cache.

Low-level utilities shared by bw_ops for interacting with the bw CLI.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import time
from typing import Any

logger = logging.getLogger(__name__)

# item_id:field_name -> (value, expiry_time) in-memory cache
_cache: dict[str, tuple[str, float]] = {}

# Status result cache (60s TTL)
_status_cache: dict[str, Any] = {}
_status_cache_expiry: float = 0
_STATUS_CACHE_TTL = 60

BW_TIMEOUT = 15  # subprocess timeout (seconds) -- bw tends to be slower than op

# ── Input Validation ───────────────────────────────────────────

_DANGEROUS_CHARS_RE = re.compile(r"[;|&`$\\<>\"'\n\r\x00]")


def validate_name(value: str, label: str) -> str | None:
    """Validate item/folder names.

    Subprocess is called in list form so shell injection risk is low,
    but reject dangerous characters as a precaution. Unicode is allowed.
    Returns error message string on failure, None on success.
    """
    if not value or not value.strip():
        return f"{label} が空です"
    if len(value) > 200:
        return f"{label} が長すぎます (200 文字以内)"
    if _DANGEROUS_CHARS_RE.search(value):
        return f"{label} に使用できない文字が含まれています"
    return None


def key_to_field_name(key: str) -> str:
    """Convert dot-notation key to bw field name.

    Example: "server.pin" -> "server_pin"
             "sns.bluesky.app_password" -> "sns_bluesky_app_password"
    """
    return key.replace(".", "_")


def parse_bw_error(stderr: str) -> str:
    """Generate a user-friendly message from bw CLI stderr."""
    lower = stderr.lower()
    if "not logged in" in lower or "unauthenticated" in lower:
        return "Bitwarden にログインされていません。bw login を実行してください"
    if "vault is locked" in lower or "locked" in lower:
        return "Bitwarden の保管庫がロックされています。bw unlock を実行してください"
    if "not found" in lower:
        return "指定されたアイテムが見つかりません"
    if "session key" in lower:
        return "セッションkeyが無効です。BW_SESSION 環境変数を確認してください"
    if "more than one" in lower or "multiple" in lower:
        return "同名のアイテムが複数存在します。アイテム ID を指定してください"
    # Return as-is
    return stderr.strip() if stderr.strip() else "不明なエラーが発生しました"


# ── CLI Utilities ─────────────────────────────────────────────


def is_available() -> bool:
    """Check whether bw CLI exists on PATH."""
    return shutil.which("bw") is not None


def _get_session() -> str | None:
    """Retrieve session key from the BW_SESSION environment variable.

    Returns None if unset (UI should prompt for setup).
    """
    session = os.environ.get("BW_SESSION")
    if session and session.strip():
        return session.strip()
    return None


def _build_session_args() -> list:
    """Return --session args if session key is available, else empty list."""
    session = _get_session()
    if session:
        return ["--session", session]
    return []


def run_bw(args: list, *, timeout: int = BW_TIMEOUT,
           stdin_data: str | None = None) -> subprocess.CompletedProcess:
    """Execute a bw command (common helper).

    Automatically appends --nointeraction and --session if available.
    """
    cmd = ["bw"] + args + ["--nointeraction"] + _build_session_args()
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        input=stdin_data,
    )


# ── Status Check ─────────────────────────────────────────────────


def get_bw_status() -> dict[str, Any]:
    """Return bw CLI authentication status (for UI display).

    Results are cached for _STATUS_CACHE_TTL seconds.

    Returns:
        {"available": bool, "signed_in": bool, "status": str,
         "user_email": str, "server_url": str,
         "has_session": bool}
    """
    global _status_cache, _status_cache_expiry

    now = time.time()
    if _status_cache and now < _status_cache_expiry:
        return _status_cache

    result = _get_bw_status_uncached()
    _status_cache = result
    _status_cache_expiry = now + _STATUS_CACHE_TTL
    return result


def _get_bw_status_uncached() -> dict[str, Any]:
    """Actually check bw CLI authentication status (no cache)."""
    import json as _json

    has_session = _get_session() is not None

    if not is_available():
        return {
            "available": False,
            "signed_in": False,
            "status": "not_installed",
            "user_email": "",
            "server_url": "",
            "has_session": has_session,
        }

    try:
        # Run bw status with --nointeraction and --session flags
        r = run_bw(["status"])
        if r.returncode != 0:
            return {
                "available": True,
                "signed_in": False,
                "status": "error",
                "user_email": "",
                "server_url": "",
                "has_session": has_session,
            }

        info = _json.loads(r.stdout)
        status = info.get("status", "unauthenticated")
        # "unlocked" -> signed in and vault unlocked
        # "locked" -> signed in but vault locked
        # "unauthenticated" -> not logged in
        signed_in = status == "unlocked"

        return {
            "available": True,
            "signed_in": signed_in,
            "status": status,
            "user_email": info.get("userEmail", ""),
            "server_url": info.get("serverUrl", ""),
            "has_session": has_session,
        }

    except subprocess.TimeoutExpired:
        logger.warning("bw status timeout (%ds)", BW_TIMEOUT)
        return {
            "available": True,
            "signed_in": False,
            "status": "timeout",
            "user_email": "",
            "server_url": "",
            "has_session": has_session,
        }
    except (FileNotFoundError, Exception) as e:
        logger.debug("bw status failed: %s", e)
        return {
            "available": False,
            "signed_in": False,
            "status": "error",
            "user_email": "",
            "server_url": "",
            "has_session": has_session,
        }


# ── Cache Management ─────────────────────────────────────────────────


def get_cache() -> dict[str, tuple[str, float]]:
    """Return the shared in-memory secret cache dict."""
    return _cache


def clear_cache() -> None:
    """Clear all in-memory caches."""
    global _status_cache, _status_cache_expiry
    _cache.clear()
    _status_cache = {}
    _status_cache_expiry = 0
