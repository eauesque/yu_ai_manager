"""1Password CLI authentication state detection.

Detects auth method (service account / biometric / manual) and
checks sign-in status via `op whoami` / `op account list`.
"""

from __future__ import annotations

import json as _json
import logging
import os
import platform
import subprocess
import time
from typing import Any

logger = logging.getLogger(__name__)

# Status result cache (60s TTL)
_status_cache: dict[str, Any] = {}
_status_cache_expiry: float = 0
_STATUS_CACHE_TTL = 60

_OP_TIMEOUT = 10  # subprocess timeout (seconds)


def _detect_auth_method() -> str:
    """Detect the current 1Password authentication method.

    Returns:
        "service_account" | "biometric" | "manual" | "none"
    """
    # Service Account Token
    if os.environ.get("OP_SERVICE_ACCOUNT_TOKEN"):
        return "service_account"

    # Biometric Unlock env var
    if os.environ.get("OP_BIOMETRIC_UNLOCK_ENABLED") == "true":
        return "biometric"

    # macOS: check for 1Password agent socket
    system = platform.system()
    if system == "Darwin":
        sock = os.path.expanduser(
            "~/Library/Group Containers/2BUA8C4S2C.com.1password/t/agent.sock",
        )
        if os.path.exists(sock):
            return "biometric"
    elif system == "Windows":
        # Windows: named pipes are hard to check directly;
        # OP_BIOMETRIC_UNLOCK_ENABLED is the primary signal
        pass

    return "manual"


def _get_op_status_uncached() -> dict[str, Any]:
    """Check op CLI authentication state without cache."""
    from .op_store import is_available

    system = platform.system()
    has_sa_token = bool(os.environ.get("OP_SERVICE_ACCOUNT_TOKEN"))

    if not is_available():
        return {
            "available": False,
            "signed_in": False,
            "account": "",
            "auth_method": "none",
            "platform": system,
            "has_service_account_token": has_sa_token,
            "has_biometric": False,
        }

    auth_method = _detect_auth_method()

    # 1) op whoami for auth check (~0.5s)
    account = ""
    signed_in = False
    try:
        r1 = subprocess.run(
            ["op", "whoami", "--format=json"],
            capture_output=True, text=True,
            timeout=_OP_TIMEOUT,
        )
        if r1.returncode == 0:
            info = _json.loads(r1.stdout)
            account = info.get("email", info.get("url", ""))
            signed_in = True
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        logger.debug("op whoami failed: %s", e)

    # 2) On whoami failure: op account list (fast ~0.5s)
    #    Account exists = Desktop App Integration is configured.
    #    Note: op vault list takes 10s+ with Desktop App Integration, so avoid it.
    if not signed_in:
        try:
            r2 = subprocess.run(
                ["op", "account", "list", "--format=json"],
                capture_output=True, text=True,
                timeout=_OP_TIMEOUT,
            )
            if r2.returncode == 0:
                accounts = _json.loads(r2.stdout)
                if accounts:
                    signed_in = True
                    account = accounts[0].get("email", accounts[0].get("url", ""))
                    if auth_method == "manual":
                        auth_method = "biometric"
                    logger.debug(
                        "op whoami failed but account list has entries "
                        "(Desktop App Integration)"
                    )
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            logger.debug("op account list failed: %s", e)

    return {
        "available": True,
        "signed_in": signed_in,
        "account": account,
        "auth_method": auth_method,
        "platform": system,
        "has_service_account_token": has_sa_token,
        "has_biometric": auth_method == "biometric",
    }


def get_op_status() -> dict[str, Any]:
    """Return op CLI authentication status (cached for UI display).

    Results are cached for _STATUS_CACHE_TTL seconds.
    Uses op whoami (fast) -> op account list (fast), avoiding
    op vault list which takes 10s+ with Desktop App Integration.
    """
    global _status_cache, _status_cache_expiry

    now = time.time()
    if _status_cache and now < _status_cache_expiry:
        return _status_cache

    result = _get_op_status_uncached()
    _status_cache = result
    _status_cache_expiry = now + _STATUS_CACHE_TTL
    return result


def clear_status_cache() -> None:
    """Clear the status result cache."""
    global _status_cache, _status_cache_expiry
    _status_cache = {}
    _status_cache_expiry = 0
