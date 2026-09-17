"""scanned-roots payload helpers for debug routes."""

import logging
import os
from collections import Counter

from core.configuration.api import load_config_json
from core.platform import resolve_real_path
from core.services_core.db_api import get_raw_db, get_readonly_db

logger = logging.getLogger(__name__)


def _load_registered_roots() -> list[str]:
    """Load registered scan roots from config, resolved through junctions.

    Uses ``resolve_real_path`` so that OS-level aliases like
    ``C:\\ユーザー`` (Japanese Windows junction for ``C:\\Users``)
    are resolved to their canonical forms before comparison.
    """
    try:
        config = load_config_json(None)
        roots = config.get("scan_roots", [])
        result = []
        for r in roots:
            p = r.get("path", "") if isinstance(r, dict) else ""
            if p:
                result.append(resolve_real_path(p))
        # Sort longest first so deeper paths match before shallower ones
        result.sort(key=len, reverse=True)
        return result
    except Exception:
        return []


def _match_registered_root(filepath: str, registered: list[str]) -> str:
    """Match a file path against registered scan roots.

    Both the filepath and registered roots are resolved through
    junctions so ``C:\\ユーザー\\...`` correctly matches a root
    registered as ``C:\\Users\\...``.
    """
    norm = resolve_real_path(filepath)
    for root in registered:
        if norm.startswith(root + os.sep) or norm == root:
            # Return the resolved root as display path
            return root
    return ""


def _extract_root_dir(filepath: str) -> str:
    """Extract root-ish directory from a file path (fallback)."""
    sep = "\\" if "\\" in filepath else "/"

    if filepath.startswith("\\\\") or filepath.startswith("//"):
        prefix = filepath[:2]
        rest = filepath[2:]
        parts = rest.split(sep)
        n = min(3, len(parts))
        return prefix + sep.join(parts[:n])

    if len(filepath) >= 3 and filepath[1] == ":" and filepath[2] == sep:
        parts = filepath[3:].split(sep)
        if parts and parts[0]:
            return filepath[:3] + parts[0]
        return filepath[:3]

    if filepath.startswith("/"):
        parts = filepath[1:].split("/")
        n = min(2, len(parts))
        return "/" + "/".join(parts[:n])

    return filepath


def scanned_roots_payload() -> tuple[dict, int]:
    """Build payload for scanned roots summary.

    Registered scan roots are tallied via SQL COUNT; only unmatched entries
    are processed in Python.
    """
    try:
        con = get_readonly_db()
        registered = _load_registered_roots()

        roots: dict[str, int] = {}
        # Cache resolve_real_path results
        _resolve_cache: dict[str, str] = {}

        def _cached_resolve(p: str) -> str:
            if p not in _resolve_cache:
                _resolve_cache[p] = resolve_real_path(p)
            return _resolve_cache[p]

        # 1. Count files per registered root in a single SUM(CASE) pass
        #    (was: one COUNT(*) full-scan per root — N+1)
        exclude_clauses: list[str] = []
        exclude_params: list[str] = []
        like_patterns: list[str] = []
        for root in registered:
            like_pat = root.rstrip("/").rstrip("\\") + "/%"
            like_patterns.append(like_pat)
            exclude_clauses.append("path NOT LIKE ?")
            exclude_params.append(like_pat)

        if like_patterns:
            select_parts = [
                "SUM(CASE WHEN path LIKE ? THEN 1 ELSE 0 END)"
                for _ in like_patterns
            ]
            counts_row = con.execute(
                "SELECT " + ", ".join(select_parts)
                + " FROM files WHERE is_deleted = 0",
                like_patterns,
            ).fetchone()
            for root, cnt in zip(registered, counts_row, strict=True):
                if cnt and cnt > 0:
                    roots[root] = cnt

        # 2. Fetch only unmatched entries and process in Python
        if exclude_clauses:
            where = "is_deleted = 0 AND " + " AND ".join(exclude_clauses)
            unmatched = con.execute(
                f"SELECT path FROM files WHERE {where}", exclude_params
            )
        else:
            unmatched = con.execute(
                "SELECT path FROM files WHERE is_deleted = 0"
            )

        unmatched_counts: Counter = Counter()
        for row in unmatched:
            rd = _extract_root_dir(row[0])
            if rd:
                unmatched_counts[rd] += 1

        # 3. Merge unmatched roots (consolidate duplicates and parent-child relationships)
        for rd, cnt in unmatched_counts.most_common(200):
            norm_rd = _cached_resolve(rd)
            merged = False
            for existing in list(roots.keys()):
                norm_ex = _cached_resolve(existing)
                if norm_rd.startswith(norm_ex + os.sep) or norm_rd == norm_ex:
                    roots[existing] += cnt
                    merged = True
                    break
                if norm_ex.startswith(norm_rd + os.sep):
                    roots[rd] = roots.pop(existing) + cnt
                    merged = True
                    break
            if not merged:
                roots[rd] = cnt

        result = [
            {"path": p, "count": c}
            for p, c in sorted(roots.items(), key=lambda x: (-x[1], x[0]))
        ][:50]
        return {"roots": result}, 200
    except Exception:
        logger.exception("Roots summary failed")
        return {"error": "Failed to compute roots summary", "code": "roots_summary_failed"}, 500


def _purge_db_root_write(like_fwd: str, like_bwd: str) -> tuple[int, int]:
    """Single-writer body for purge_db_root.

    Must run on the dedicated DB writer thread (via submit_db_write) so it
    does not race with other writers for the WAL write lock.
    """
    con = get_raw_db()

    # Clear self-referencing FK (extracted_to_file_id) before delete
    con.execute(
        "UPDATE files SET extracted_to_file_id = NULL "
        "WHERE extracted_to_file_id IN ("
        "  SELECT id FROM files WHERE path LIKE ? OR path LIKE ?"
        ")",
        (like_fwd, like_bwd),
    )

    cur = con.execute(
        "DELETE FROM files WHERE path LIKE ? OR path LIKE ?",
        (like_fwd, like_bwd),
    )
    purged = cur.rowcount

    # cleanup_prune_unused_tags does not commit internally, so we fold it
    # into the same transaction as the file delete to keep them atomic
    from core.cleanup_core.cleanup_files import cleanup_prune_unused_tags
    pruned_tags = cleanup_prune_unused_tags(con, dry_run=False)
    con.commit()

    return purged, pruned_tags


def purge_db_root(root_path: str) -> tuple[dict, int]:
    """Delete all files (and CASCADE-related rows) under root_path."""
    if not root_path or not root_path.strip():
        return {"error": "path is required", "code": "path_required"}, 400

    root_path = root_path.strip()
    # Normalize: match both / and \\ variants
    fwd = root_path.replace("\\", "/")
    bwd = root_path.replace("/", "\\")
    like_fwd = fwd.rstrip("/") + "/%"
    like_bwd = bwd.rstrip("\\") + "\\%"

    try:
        from core.services_core.db_write import submit_db_write
        purged, pruned_tags = submit_db_write(_purge_db_root_write, like_fwd, like_bwd)

        logger.info("Purged %d files under %s (pruned %d tags)", purged, root_path, pruned_tags)

        from core.event_bus import emit
        from core.event_bus.event_types import SCAN_ROOTS_CHANGED
        emit(SCAN_ROOTS_CHANGED, {"action": "purge", "path": root_path})

        # Invalidate server-info stats cache (file_count changed)
        from core.search_api.server_info import invalidate_stats_cache
        invalidate_stats_cache()

        return {"purged": purged, "path": root_path}, 200
    except Exception as exc:
        logger.error("purge_db_root failed: %s", exc, exc_info=True)
        return {"error": "Purge failed", "code": "purge_failed"}, 500
