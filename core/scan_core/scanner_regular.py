"""Regular-file scan implementation."""

import sqlite3
import time
from pathlib import Path
from typing import Any

from core.infra_core.file_hash import file_etag
from core.models_core.models_files import get_file_row, upsert_file
from core.platform import normalize_path
from core.scan.common import should_rescan
from core.schema_core.schema_constants import CURRENT_PARSER_VERSION
from core.services_core.media_extract_state import mark_media_extract_state_stale

from .scanner_io import extract_resolution
from .scanner_regular_extract import extract_regular_metadata
from .scanner_regular_persist import persist_regular_scan_result

# Emit a per-step dlog when scan_one_regular for a single file takes
# longer than this. Tuned to catch auto-import outliers (2s NAI generates
# observed in prod) without flooding the log on normal scans.
_SCAN_SLOW_LOG_MS = 500.0

# Return type: ("added"|"updated"|"backfilled", file_id) or None (skipped)
ScanResult = tuple[str, int] | None


def _needs_template_repair(con: sqlite3.Connection, file_id: int) -> bool:
    """Return True if a file has tags but no template (partial import)."""
    row = con.execute(
        """SELECT 1 FROM file_tags WHERE file_id=? AND source='meta'
           LIMIT 1""",
        (file_id,),
    ).fetchone()
    if row is None:
        return False
    tmpl = con.execute(
        "SELECT 1 FROM templates WHERE file_id=? LIMIT 1",
        (file_id,),
    ).fetchone()
    return tmpl is None


def _backfill_hashes(
    con: sqlite3.Connection, p: Path, file_id: int, old_hash: str | None
) -> ScanResult:
    """Compute missing content hash for an unchanged file (BUG-62).

    Called when should_rescan() returns False but hash is NULL.
    Only fills content hash (fast ~5ms) -- phash is handled by the
    dedicated compute-hashes job to keep scans fast.
    """
    if old_hash is not None:
        return None

    new_hash = file_etag(p)
    if new_hash:
        cur = con.execute("UPDATE files SET hash=? WHERE id=? AND hash IS NOT ?", (new_hash, file_id, new_hash))
        if cur.rowcount:
            return ("backfilled", file_id)
    return None


def scan_one_regular(con: sqlite3.Connection, p: Path, config: dict[str, Any], force: bool, compute_hash: bool, *, skip_backfill: bool = False) -> ScanResult:
    _t_total = time.perf_counter()
    _steps: dict[str, float] = {}

    def _mark(name: str, t0: float) -> None:
        _steps[name] = round((time.perf_counter() - t0) * 1000, 1)

    _t = time.perf_counter()
    st = p.stat()
    path_s = normalize_path(p)
    mtime = int(st.st_mtime)
    size = int(st.st_size)
    if size == 0:
        return None
    _mark("stat", _t)

    _t = time.perf_counter()
    existing = get_file_row(con, path_s)
    _mark("get_file_row", _t)
    old_hash = existing[4] if existing else None
    _t = time.perf_counter()
    _should = should_rescan(con, path_s, mtime, size, force=force)
    _mark("should_rescan", _t)
    if not _should:
        # BUG-62: Backfill hash/phash for unchanged files with NULL values.
        # Always attempt backfill regardless of compute_hash flag —
        # fixing missing hashes is a data-integrity operation, not an
        # opt-in feature.  _backfill_hashes only touches NULL columns.
        # skip_backfill: set True when COUNT query at scan start found 0
        # files needing backfill — avoids per-file overhead.
        if existing and not skip_backfill:
            backfill_result = _backfill_hashes(con, p, existing[0], old_hash)
            if backfill_result is not None:
                return backfill_result
        # Repair: rescan files left in partial state (file+tags but no template)
        if existing and _needs_template_repair(con, existing[0]):
            force = True
        else:
            return None

    is_new = existing is None

    stale_media_state = False
    if existing:
        old_mtime, old_size = existing[1], existing[2]
        if old_mtime != mtime or old_size != size:
            stale_media_state = True

    new_hash: str | None = None
    if compute_hash:
        new_hash = file_etag(p)
        if (not force) and old_hash and new_hash == old_hash:
            if stale_media_state and existing:
                mark_media_extract_state_stale(
                    con,
                    int(existing[0]),
                    mtime=mtime,
                    size=size,
                    content_hash=new_hash,
                )
            # BUG-58: Preserve original meta_source; only update mtime/size/hash + parser_version
            con.execute(
                """
                UPDATE files
                SET mtime=?, size=?, hash=?, not_modified=1, parser_version=?
                WHERE path=?
                  AND (
                    mtime IS NOT ?
                    OR size IS NOT ?
                    OR hash IS NOT ?
                    OR not_modified IS NOT 1
                    OR parser_version IS NOT ?
                  )
                """,
                (mtime, size, new_hash, CURRENT_PARSER_VERSION, path_s, mtime, size, new_hash, CURRENT_PARSER_VERSION),
            )
            return None

    if stale_media_state and existing:
        mark_media_extract_state_stale(
            con,
            int(existing[0]),
            mtime=mtime,
            size=size,
            content_hash=old_hash,
        )

    _t = time.perf_counter()
    meta_source, fmt, raw_prompt, raw_negative, raw_meta_json, tag_source = extract_regular_metadata(p)
    _mark("extract_metadata", _t)

    _t = time.perf_counter()
    img_width, img_height = extract_resolution(raw_prompt, raw_meta_json)

    # SVG: extract dimensions from the SVG file itself (no AI metadata)
    if img_width is None and p.suffix.lower() == ".svg":
        from core.files_core.svg_raster import get_svg_dimensions
        img_width, img_height = get_svg_dimensions(p)
    _mark("extract_resolution", _t)

    _t = time.perf_counter()
    file_id = upsert_file(
        con, path_s, mtime, size, meta_source, content_hash=new_hash, width=img_width, height=img_height
    )
    _mark("upsert_file", _t)

    _t = time.perf_counter()
    persist_regular_scan_result(
        con,
        p,
        file_id,
        config,
        meta_source,
        fmt,
        raw_prompt,
        raw_negative,
        raw_meta_json,
        tag_source,
        mtime=mtime,
    )
    _mark("persist", _t)

    total_ms = round((time.perf_counter() - _t_total) * 1000, 1)
    if total_ms >= _SCAN_SLOW_LOG_MS:
        # Surface the per-step breakdown so we can locate the bottleneck
        # in slow paths like NAI auto-import (2s+ per file observed).
        from core.infra_core.debug_log import dlog
        dlog(
            "scan",
            "scan_one_regular.slow",
            path=path_s,
            total_ms=total_ms,
            meta_source=meta_source,
            **{f"{k}_ms": v for k, v in _steps.items()},
        )
    return ("added" if is_new else "updated", file_id)
