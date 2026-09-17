"""Single-file Hailo Remote Tagger operations.

Tag one file: validate -> send to Pi -> filter by threshold -> save to DB.
"""

from __future__ import annotations

import logging
from pathlib import Path

from core.services_core.db_state import get_readonly_db

logger = logging.getLogger(__name__)


def _get_hailo_config() -> dict:
    """Load hailo_tagger config section with defaults."""
    from core.configuration.json_rw import load_config_json
    cfg = load_config_json(None)
    ht = cfg.get("hailo_tagger", {})
    return {
        "enabled": ht.get("enabled", False),
        "endpoint_url": ht.get("endpoint_url", "").strip(),
        "threshold": float(ht.get("threshold", 0.35)),
        "timeout": int(ht.get("timeout", 30)),
    }


def tag_one_file(file_id: int, force: bool = False) -> dict:
    """Run Hailo Remote Tagger on a single file.

    Args:
        file_id: Database file ID
        force: If True, re-tag even if tags already exist

    Returns:
        dict with tag results or error info
    """
    from core.files_core.media_types import is_taggable_file

    from .http_client import call_hailo_tagger
    from .store import get_hailo_tags, save_hailo_tags

    config = _get_hailo_config()
    if not config["enabled"]:
        return {"error": "Hailo Remote Tagger is disabled", "code": "disabled"}
    if not config["endpoint_url"]:
        return {"error": "Hailo endpoint URL not configured", "code": "not_configured"}

    # Validate file exists and is not deleted
    con = get_readonly_db()
    row = con.execute(
        "SELECT id, path, meta_source FROM files WHERE id = ? AND is_deleted = 0",
        (file_id,),
    ).fetchone()
    if not row:
        return {"error": "File not found or deleted", "code": "file_not_found"}

    filepath = row["path"]

    # Check if file exists on disk
    if not Path(filepath).exists():
        return {"error": "File not found on disk", "code": "file_missing"}

    # Skip non-taggable files
    if not is_taggable_file(filepath):
        return {"error": "File type not supported for tagging", "code": "unsupported_type"}

    # Check if already tagged (unless force)
    if not force:
        existing = get_hailo_tags(file_id)
        if existing:
            return {
                "skipped": True,
                "reason": "already_tagged",
                "tag_count": len(existing),
            }

    # Call remote Hailo tagger
    try:
        raw_tags = call_hailo_tagger(
            filepath,
            config["endpoint_url"],
            timeout=config["timeout"],
        )
    except Exception as exc:
        logger.error("Hailo tagger request failed for file %d: %s", file_id, exc)
        return {
            "error": f"Hailo tagger request failed: {exc}",
            "code": "request_failed",
            "status_code": 502,
        }

    # Apply threshold filter
    threshold = config["threshold"]
    filtered = [t for t in raw_tags if float(t.get("confidence", 0)) >= threshold]

    # Save to DB
    tag_count = save_hailo_tags(file_id, filtered)

    logger.info("Hailo-tagged file %d: %d tags (threshold=%.2f)", file_id, tag_count, threshold)

    return {
        "file_id": file_id,
        "filepath": filepath,
        "tag_count": tag_count,
        "tags": filtered,
    }
