"""Per-IP API rate limiter with three tiers (token bucket, no external deps).

Tier design:
  - HEAVY:      CPU/IO intensive   (scan, similar, hash, AI)  ~20 req/min burst 5
  - DESTRUCTIVE: data-loss risk    (purge, hard-delete, config write)  ~12 req/min burst 3
  - WRITE:      mutation endpoints (batch-set, toggle, create)  ~120 req/min burst 30
  - (none):     read-only GET      unlimited

Read-only browsing (search, thumbnails, metadata) is intentionally
unlimited because thumbnail grids fire hundreds of concurrent requests
and browsers don't retry failed <img> loads.
"""

from __future__ import annotations

import threading
import time


class TokenBucket:
    """Single token bucket for one tier."""

    __slots__ = ("rate", "burst", "_buckets", "_lock", "_check_count",
                 "_max_ips", "_stale_seconds")

    def __init__(self, rate: float, burst: int,
                 max_ips: int = 10000, stale_seconds: int = 300):
        self.rate = rate
        self.burst = burst
        self._max_ips = max_ips
        self._stale_seconds = stale_seconds
        # Per-IP: [tokens, last_access_time]
        self._buckets: dict[str, list[float]] = {}
        self._lock = threading.Lock()
        self._check_count = 0

    def check(self, ip: str) -> tuple[bool, int]:
        """Consume one token. Returns (allowed, remaining)."""
        now = time.time()
        with self._lock:
            self._check_count += 1
            if self._check_count % 500 == 0:
                self._evict_stale(now)

            bucket = self._buckets.get(ip)
            if bucket is None:
                if len(self._buckets) >= self._max_ips:
                    self._evict_stale(now)
                    if len(self._buckets) >= self._max_ips:
                        self._evict_oldest()
                bucket = [float(self.burst), now]
                self._buckets[ip] = bucket

            elapsed = now - bucket[1]
            bucket[1] = now
            bucket[0] = min(self.burst, bucket[0] + elapsed * self.rate)

            if bucket[0] < 1.0:
                return False, 0
            bucket[0] -= 1.0
            return True, int(bucket[0])

    def _evict_stale(self, now: float) -> None:
        cutoff = now - self._stale_seconds
        stale = [ip for ip, b in self._buckets.items() if b[1] < cutoff]
        for ip in stale:
            del self._buckets[ip]

    def _evict_oldest(self) -> None:
        if not self._buckets:
            return
        oldest_ip = min(self._buckets, key=lambda k: self._buckets[k][1])
        del self._buckets[oldest_ip]


# ── Tier singletons ──────────────────────────────────────────────

heavy_limiter = TokenBucket(rate=0.33, burst=5)        # ~20 req/min
destructive_limiter = TokenBucket(rate=0.2, burst=3)    # ~12 req/min
write_limiter = TokenBucket(rate=2.0, burst=30)         # ~120 req/min


# ── Path classification ──────────────────────────────────────────

# CPU/IO intensive operations
HEAVY_PATHS = (
    "/api/tools/archive-cleanup/scan",
    "/api/tools/archive-cleanup/llm-verify",
    "/api/tools/archive-cleanup/llm-verify-batch",
    "/api/tools/find-similar",
    "/api/tools/compute-hashes",
    "/api/analysis/analyze",
    "/api/analysis/batch",
    "/api/scan/start",
    "/api/scan-all",
    "/api/wd-tagger/tag/",
    "/api/wd-tagger/batch",
    "/api/wd-tagger/model/download",
    "/ext/hailo-semantic/api/index/start",
    "/ext/hailo-yolo/api/detect/start",
    "/ext/hailo-yolo/api/detect/search",
    "/ext/hailo-yolo/api/model/download",
    "/ext/hailo-genai/api/llm/generate",
    "/ext/hailo-genai/api/vlm/generate",
    "/ext/hailo-genai/api/s2t/transcribe",
    "/ext/hailo-genai/api/model/download",
    "/ext/freeze-pullback/api/generate",
    "/api/download/batch-zip",
    "/api/sns/bluesky/post",
    "/api/sns/bluesky/test",
)

# Destructive on EVERY method, GET included: reading these is itself the
# sensitive act, so they must not fall through to the unlimited GET branch.
#
# Checked before DESTRUCTIVE_PATHS because classification is `startswith`:
# "/api/settings/config" would otherwise also cover "/api/settings/config-toml"
# and hand its GET the mutating-only treatment.
DESTRUCTIVE_PATHS_ALL_METHODS = (
    # GET returns the config file verbatim -- api_keys, webhook_secret,
    # server.pin and the rest, deliberately unredacted because the editor
    # round-trips what it is given. Reading it IS the sensitive operation.
    "/api/settings/config-toml",
)

# Destructive when they MUTATE. A GET on these is a plain read and is not
# limited: the tier is checked before the GET exemption below, so a read used
# to draw on the same ~12/min budget as the write, and a session that reloaded
# its own settings a few times was refused its own configuration.
#
# Verified 2026-09-02 that this is safe for every entry: all of them are
# POST-only except the config/sns reads this change is for. In particular
# `/api/settings/secrets/export` -- the one whose GET would have exfiltrated
# the secret store -- is `methods=["POST"]`, so no GET reaches it at all.
DESTRUCTIVE_PATHS = (
    "/api/scanned-roots/purge",
    "/api/tools/archive-cleanup/execute",
    "/api/tools/delete-duplicates",
    "/api/tools/clear-cache",
    "/api/tools/rebuild-groups",
    "/api/settings/config",          # config overwrite
    "/api/settings/config/legacy-migration",
    "/api/tools/backup/create",
    "/api/tools/backup/restore",
    "/api/tools/backup/delete",
    "/ext/hailo-yolo/api/detect/clear",
    "/api/sns/config",
    "/api/settings/secrets/export",
    "/api/settings/secrets/import",
    "/api/settings/secrets/migrate-keychain",
    "/api/settings/secrets/push-to-op",
    "/api/system/update/apply",
)

# DELETE on these prefixes triggers auto-purge or significant side effects
DESTRUCTIVE_DELETE_PREFIXES = (
    "/api/scan-roots/",              # auto-purges DB records
    "/api/scheduler/jobs/",          # job removal
)

# Write endpoints that don't need tight limits individually
# but should still be capped to prevent spam.
# Matched by: POST/PUT/DELETE on /api/ (not in HEAVY or DESTRUCTIVE)
# This is applied generically by method check, no explicit path list needed.


def get_client_ip() -> str:
    """Get the real client IP of the request origin.

    Only trusts X-Forwarded-For when trusted_proxy_ips is configured,
    returning the last untrusted address in the chain.
    Falls back to request.remote_addr when not configured (safe default).
    """
    from quart import current_app, request

    trusted_ips = current_app.config.get("TRUSTED_PROXY_IPS", set())
    if not trusted_ips:
        return request.remote_addr or "unknown"

    # request.access_route: parsed list from X-Forwarded-For + remote_addr
    # Skip trusted proxies from the end, return the first untrusted address
    access_route = request.access_route
    if not access_route:
        return request.remote_addr or "unknown"

    # If remote_addr itself is not a trusted proxy, return it as-is
    if request.remote_addr not in trusted_ips:
        return request.remote_addr or "unknown"

    # Scan right-to-left, return the first non-trusted IP
    for ip in reversed(access_route):
        ip = ip.strip()
        if ip not in trusted_ips:
            return ip

    # All IPs are trusted (unlikely, but safe fallback)
    return access_route[0].strip()


def classify(method: str, path: str) -> TokenBucket | None:
    """Return the limiter for a request, or None if unlimited."""
    is_api = path.startswith("/api/") or path.startswith("/ext/")
    if not is_api:
        return None

    # Tier 1: heavy compute
    if any(path.startswith(p) for p in HEAVY_PATHS):
        return heavy_limiter

    # Tier 2: destructive operations
    is_read = method in ("GET", "HEAD", "OPTIONS")
    # These are sensitive to read as well as to write, so they come first and
    # ignore the method entirely.
    if any(path.startswith(p) for p in DESTRUCTIVE_PATHS_ALL_METHODS):
        return destructive_limiter
    if not is_read and any(path.startswith(p) for p in DESTRUCTIVE_PATHS):
        return destructive_limiter
    if method == "DELETE" and any(path.startswith(p) for p in DESTRUCTIVE_DELETE_PREFIXES):
        return destructive_limiter

    # Tier 3: other mutations (POST/PUT/DELETE)
    if method not in ("GET", "HEAD", "OPTIONS"):
        return write_limiter

    # GET/HEAD/OPTIONS on non-heavy paths: unlimited
    return None
