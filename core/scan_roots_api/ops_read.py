"""Read/query operations for scan roots config."""

import os
from typing import Any

from core.configuration.api import load_config_json
from core.infra_core.simple_ttl_cache import SimpleTTLCache
from core.services_core.db_state import get_readonly_db

# Tool/Settings ページの 3〜4 モジュールが /api/scan-roots を独立フェッチして
# 直列化するため、LIKE フルスキャンを 30 秒キャッシュして起動遅延を抑える。
_FILE_COUNT_CACHE = SimpleTTLCache(ttl_seconds=30.0)


def _count_files_under(path: str) -> int:
    """Return the number of non-deleted files under *path* in the DB."""

    def _query() -> int:
        try:
            con = get_readonly_db()
            norm = path.replace("\\", "/").rstrip("/")
            # idx_files_deleted_path (is_deleted, path) を BINARY collation で
            # 範囲スキャンに乗せる: '/' (0x2F) の次は '0' (0x30)、'\' (0x5C) の
            # 次は ']' (0x5D)。LIKE 'X/%' OR LIKE 'X\%' (フルスキャン相当) を
            # MULTI-INDEX OR の二回 range seek に置き換え。
            fwd_lo = norm + "/"
            fwd_hi = norm + "0"
            bck = norm.replace("/", "\\")
            bck_lo = bck + "\\"
            bck_hi = bck + "]"
            row = con.execute(
                "SELECT COUNT(*) FROM files WHERE is_deleted=0 AND ("
                "(path >= ? AND path < ?) OR (path >= ? AND path < ?))",
                (fwd_lo, fwd_hi, bck_lo, bck_hi),
            ).fetchone()
            return row[0] if row else 0
        except Exception:
            return 0

    return _FILE_COUNT_CACHE.get_or_compute(path, _query)


def invalidate_scan_root_file_count_cache() -> None:
    """Drop cached counts (call after scan completion or root mutation)."""
    _FILE_COUNT_CACHE.invalidate()


def get_scan_roots_with_exists() -> list[dict[str, Any]]:
    config = load_config_json(None)
    roots = config.get("scan_roots", [])
    for root in roots:
        exists = os.path.exists(root["path"])
        root["exists"] = exists
        root["file_count"] = _count_files_under(root["path"])
        if not exists and root.get("enabled", True):
            root["warning"] = "Path not found"
    return roots


def load_enabled_scan_roots():
    config = load_config_json(None)
    roots = config.get("scan_roots", [])
    enabled_roots = [r for r in roots if r.get("enabled", True)]
    return roots, enabled_roots
