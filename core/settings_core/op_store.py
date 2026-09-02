"""1Password CLI (op) integration: dynamic secret retrieval via op read.

Resolves URIs from config.json op_secrets mapping and fetches secrets
via op CLI. Falls back to local encrypted store (secret_store) when
op CLI is not available.

This module is the public API facade. Implementation is split into:
- op_store_auth: authentication state detection
- op_store_write: vault listing and secret push
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from typing import Any

# Re-export auth functions (preserves existing import paths)
from .op_store_auth import (
    clear_status_cache,
    get_op_status,
)

# Re-export write functions (preserves existing import paths)
from .op_store_write import (
    list_vaults,
    push_secrets_to_op,
)

logger = logging.getLogger(__name__)

# URI -> (value, expiry_time) in-memory cache
_cache: dict[str, tuple[str, float]] = {}

_OP_TIMEOUT = 10  # subprocess timeout (seconds)


def is_available() -> bool:
    """Check if op CLI exists on PATH."""
    return shutil.which("op") is not None


def read_secret(uri: str, ttl: int = 300) -> str | None:
    """Fetch a secret from 1Password via op read.

    Returns cached value within TTL seconds.
    Returns None on error.

    Args:
        uri: 1Password URI (e.g. "op://Private/YuManager/pin")
        ttl: Cache duration in seconds (default 300)
    """
    # Strip quotes from pasted input
    uri = uri.strip().strip('"').strip("'")

    now = time.time()

    # Cache hit
    if uri in _cache:
        value, expiry = _cache[uri]
        if now < expiry:
            return value

    if not is_available():
        logger.warning("op CLI not found")
        return None

    try:
        result = subprocess.run(
            ["op", "read", uri],
            capture_output=True, text=True,
            timeout=_OP_TIMEOUT,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "not signed in" in stderr.lower():
                logger.warning("op: sign-in required")
            elif "could not be found" in stderr.lower():
                logger.warning("op: item not found: %s", uri)
            else:
                logger.warning("op read failed: %s", stderr)
            return None

        value = result.stdout.strip()
        _cache[uri] = (value, now + ttl)
        return value

    except subprocess.TimeoutExpired:
        logger.warning("op read timeout (%ds): %s", _OP_TIMEOUT, uri)
        return None
    except FileNotFoundError:
        logger.warning("op CLI not found")
        return None


def resolve_secret(key: str, config: dict[str, Any]) -> str | None:
    """Resolve a secret key via config's op_secrets mapping and op read.

    Returns None if the key is not in op_secrets (use local value).

    Args:
        key: Dotted key notation (e.g. "server.pin")
        config: config.json dict
    """
    op_map = config.get("op_secrets", {})
    if not isinstance(op_map, dict):
        return None

    uri = op_map.get(key)
    if not uri:
        return None

    return read_secret(uri)


def clear_cache() -> None:
    """Clear all in-memory caches (secrets + status)."""
    _cache.clear()
    clear_status_cache()


# Public API
__all__ = [
    "is_available",
    "get_op_status",
    "read_secret",
    "resolve_secret",
    "clear_cache",
    "list_vaults",
    "push_secrets_to_op",
]
