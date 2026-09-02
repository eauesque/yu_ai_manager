"""PIN auth and quick-lock state primitives."""

import hashlib
import hmac
import json
import os
import time


def hash_pin(pin: str, salt: str = "") -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", pin.encode(), f"{salt}:pin".encode(), iterations=600_000
    ).hex()


def make_token(pin: str, secret: str) -> str:
    return hmac.new(secret.encode(), pin.encode(), hashlib.sha256).hexdigest()


class RateLimiter:
    """Simple lockout on repeated failures."""

    MAX_IPS = 5000  # Cap tracked IPs to prevent memory exhaustion

    def __init__(self, max_attempts: int = 5, lockout_seconds: int = 60):
        self.max_attempts = max_attempts
        self.lockout_seconds = lockout_seconds
        self._attempts = {}

    def _evict_stale(self, now: float) -> None:
        """Remove expired entries to keep memory bounded."""
        stale = [
            ip for ip, (_, ts) in self._attempts.items()
            if now - ts > self.lockout_seconds
        ]
        for ip in stale:
            del self._attempts[ip]

    def check(self, ip: str) -> bool:
        if ip not in self._attempts:
            return True
        count, first_time = self._attempts[ip]
        if time.time() - first_time > self.lockout_seconds:
            del self._attempts[ip]
            return True
        return count < self.max_attempts

    def record_failure(self, ip: str):
        now = time.time()
        if ip in self._attempts:
            count, first_time = self._attempts[ip]
            if now - first_time > self.lockout_seconds:
                self._attempts[ip] = (1, now)
            else:
                self._attempts[ip] = (count + 1, first_time)
        else:
            # Evict stale entries if we hit the cap
            if len(self._attempts) >= self.MAX_IPS:
                self._evict_stale(now)
                # Still full — drop oldest entry
                if len(self._attempts) >= self.MAX_IPS:
                    oldest = min(self._attempts, key=lambda k: self._attempts[k][1])
                    del self._attempts[oldest]
            self._attempts[ip] = (1, now)

    def clear(self, ip: str):
        self._attempts.pop(ip, None)

    def remaining_seconds(self, ip: str) -> int:
        if ip not in self._attempts:
            return 0
        count, first_time = self._attempts[ip]
        if count < self.max_attempts:
            return 0
        elapsed = time.time() - first_time
        remaining = self.lockout_seconds - elapsed
        return max(0, int(remaining))


class QuickLock:
    """Application lock state."""

    def __init__(self):
        self._locked = False
        self._locked_at = None

    @property
    def is_locked(self) -> bool:
        return self._locked

    def lock(self):
        self._locked = True
        self._locked_at = time.time()

    def unlock(self):
        self._locked = False
        self._locked_at = None

    def info(self) -> dict:
        return {
            "locked": self._locked,
            "locked_at": self._locked_at,
            "locked_duration": int(time.time() - self._locked_at) if self._locked_at else 0,
        }


rate_limiter = RateLimiter()
quick_lock = QuickLock()


def _load_settings() -> dict:
    """Read settings.json, returning {} on any error."""
    path = os.environ.get("YU_AI_SETTINGS_PATH", "settings.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def approval_pin_source() -> str:
    """Return 'boss' or 'dedicated' from settings; default 'boss'."""
    s = _load_settings()
    return (s.get("lan_cowork", {}).get("approval_pin_source") or "boss").strip().lower()


def is_approval_pin_expired(now: int | None = None) -> bool:
    """True if the currently-configured ApprovalPIN source is past TTL."""
    now_ts = int(now if now is not None else time.time())
    s = _load_settings()
    src = approval_pin_source()
    if src == "dedicated":
        ttl = s.get("lan_cowork", {}).get("dedicated_approval_pin_ttl_days")
        set_at = s.get("lan_cowork", {}).get("dedicated_approval_pin_set_at")
    else:
        ttl = s.get("boss_mode", {}).get("pin_ttl_days")
        set_at = s.get("boss_mode", {}).get("pin_set_at")
    if ttl is None or set_at is None:
        return False  # null TTL = no expiry
    try:
        return now_ts > int(set_at) + int(ttl) * 86400
    except (TypeError, ValueError):
        return False


def verify_approval_pin(submitted: str, salt: str) -> bool:
    """Verify submitted PIN against the active source (boss or dedicated).

    Caller must pass the app secret (--secret value) as salt.
    boss_mode.pin_hash in settings.json must have been written using hash_pin() with the same salt.
    """
    s = _load_settings()
    src = approval_pin_source()
    if src == "dedicated":
        stored = s.get("lan_cowork", {}).get("dedicated_approval_pin_hash")
    else:
        stored = s.get("boss_mode", {}).get("pin_hash")
    if not stored:
        return False
    return hmac.compare_digest(hash_pin(submitted, salt), stored)
