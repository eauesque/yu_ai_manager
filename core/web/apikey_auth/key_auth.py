"""Bearer token verification middleware for API key auth."""

from __future__ import annotations

import threading
import time

from quart import request

from .key_store import verify_key


class _RateLimiter:
    """Simple per-key rate limiter (sliding window)."""

    def __init__(self, max_requests: int = 120, window_seconds: int = 60) -> None:
        self._lock = threading.Lock()
        self._max = max_requests
        self._window = window_seconds
        self._hits: dict[str, list] = {}

    def check(self, key_id: str) -> tuple[bool, int]:
        """Returns (allowed, remaining). Prunes expired entries."""
        now = time.time()
        cutoff = now - self._window
        with self._lock:
            timestamps = self._hits.get(key_id, [])
            timestamps = [t for t in timestamps if t > cutoff]
            if len(timestamps) >= self._max:
                self._hits[key_id] = timestamps
                return False, 0
            timestamps.append(now)
            self._hits[key_id] = timestamps
            return True, self._max - len(timestamps)


api_key_limiter = _RateLimiter()


def extract_bearer_token() -> str | None:
    """Extract Bearer token from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return None


def authenticate_api_key() -> dict | None:
    """Try to authenticate via API key.

    Returns key info dict if valid, None if no key or invalid.
    Does NOT produce error responses — caller decides what to do.
    """
    token = extract_bearer_token()
    if not token:
        return None
    return verify_key(token)


def check_api_key_rate_limit(key_info: dict) -> tuple[bool, int]:
    """Check rate limit for an authenticated API key."""
    return api_key_limiter.check(key_info["id"])
