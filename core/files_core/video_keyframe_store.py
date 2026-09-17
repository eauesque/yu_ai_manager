"""Per-keyframe results storage for video content analysis.

CRUD operations on the file_keyframes table.
Each keyframe record stores optional CLIP vector and WD-Tagger tags.
"""

import json
import logging
from typing import Any

from core.services_core.db_state import get_db, get_readonly_db
from core.services_core.db_write import submit_db_write

logger = logging.getLogger(__name__)


def save_keyframe_results(
    file_id: int,
    keyframes_data: list[dict[str, Any]],
    model: str = "",
) -> int:
    """Save per-keyframe results to file_keyframes.

    Args:
        file_id: Database file ID.
        keyframes_data: List of dicts with keys:
            keyframe_idx (int), timestamp_ms (int),
            vector (optional bytes), wd_tags (optional list of dicts).
        model: Model identifier string.

    Returns:
        Number of keyframes saved.
    """
    params = []
    for kf in keyframes_data:
        idx = kf.get("keyframe_idx", 0)
        ts_ms = kf.get("timestamp_ms", 0)
        vector = kf.get("vector")  # bytes or None
        wd_tags = kf.get("wd_tags")
        wd_tags_json = json.dumps(wd_tags, ensure_ascii=False) if wd_tags else None
        params.append((file_id, idx, ts_ms, vector, wd_tags_json, model))

    def _write() -> int:
        con = get_db()
        if params:
            con.executemany(
                """INSERT INTO file_keyframes
                       (file_id, keyframe_idx, timestamp_ms, vector, wd_tags_json, model)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(file_id, keyframe_idx, model) DO UPDATE SET
                       timestamp_ms = excluded.timestamp_ms,
                       vector = excluded.vector,
                       wd_tags_json = excluded.wd_tags_json,
                       created_at = strftime('%s','now')""",
                params,
            )
        con.commit()
        return len(params)

    saved = submit_db_write(_write)
    logger.debug("Saved %d keyframes for file_id=%d model=%s", saved, file_id, model)
    return saved


def get_keyframe_results(
    file_id: int, model: str | None = None,
) -> list[dict[str, Any]]:
    """Get per-keyframe results for a file.

    Returns list of dicts sorted by keyframe_idx.
    """
    con = get_readonly_db()
    if model is not None:
        rows = con.execute(
            """SELECT keyframe_idx, timestamp_ms, vector, wd_tags_json, model, created_at
               FROM file_keyframes WHERE file_id = ? AND model = ?
               ORDER BY keyframe_idx""",
            (file_id, model),
        )
    else:
        rows = con.execute(
            """SELECT keyframe_idx, timestamp_ms, vector, wd_tags_json, model, created_at
               FROM file_keyframes WHERE file_id = ?
               ORDER BY keyframe_idx""",
            (file_id,),
        )

    results = []
    for r in rows:
        tags = None
        if r["wd_tags_json"]:
            try:
                tags = json.loads(r["wd_tags_json"])
            except (json.JSONDecodeError, TypeError):
                tags = None
        results.append({
            "keyframe_idx": r["keyframe_idx"],
            "timestamp_ms": r["timestamp_ms"],
            "has_vector": r["vector"] is not None,
            "wd_tags": tags,
            "model": r["model"],
            "created_at": r["created_at"],
        })
    return results


def delete_keyframe_results(file_id: int) -> int:
    """Delete all keyframe data for a file. Returns deleted count."""
    def _write() -> int:
        con = get_db()
        cur = con.execute("DELETE FROM file_keyframes WHERE file_id = ?", (file_id,))
        con.commit()
        return cur.rowcount

    return submit_db_write(_write)


def count_files_with_keyframes() -> int:
    """Count distinct files that have keyframe analysis data."""
    con = get_readonly_db()
    row = con.execute(
        "SELECT COUNT(DISTINCT file_id) FROM file_keyframes"
    ).fetchone()
    return row[0] if row else 0
