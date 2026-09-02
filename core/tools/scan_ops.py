"""Tools scan API operations."""

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

from core.cleanup_core.cleanup import cleanup_normalize_tags
from core.services_core.db_api import get_db_path, get_raw_db
from core.tagdb_core.tool.tagdb_tool_impl import cmd_scan


def run_tools_scan(path: str, recursive: bool, scan_zips: bool, compute_hash: bool) -> tuple[dict[str, Any], int]:
    if not path:
        return {"error": "Path required"}, 400

    import argparse

    args = argparse.Namespace(
        db=str(get_db_path()),
        root=path,
        recursive=recursive,
        scan_zips=scan_zips,
        exts=".png,.jpg,.jpeg,.webp,.jxl,.avif,.heif,.heic,.svg,.webm,.mp4,.mov,.m4v,.avi,.mkv,.ogv,.mp3,.wav,.ogg,.opus,.m4a,.aac,.flac,.pdf",
        mark_deleted=False,
        force=False,
        compute_hash=compute_hash,
        config=None,
    )

    start_time = time.time()
    try:
        cmd_scan(args)
        duration = time.time() - start_time

        try:
            con2 = get_raw_db()
            normalized_count = cleanup_normalize_tags(con2, dry_run=False)
            if normalized_count > 0:
                logger.info(f"[Scan] Auto-normalized {normalized_count} tags")
        except Exception as e2:
            logger.info(f"[Scan] Tag normalization skipped: {e2}")

        con = get_raw_db()
        file_count = con.execute("SELECT COUNT(*) FROM files WHERE is_deleted=0").fetchone()[0]
        return {"processed": file_count, "duration": duration}, 200
    except Exception as e:
        logger.error(f"Scan failed: {e}", exc_info=True)
        return {"error": "Scan failed"}, 500
