"""Caption text builder for LoRA training datasets.

Reads WD-Tagger tags from file_wd_tags, filters out excluded tags,
and produces comma-separated caption text compatible with kohya_ss.
"""

from __future__ import annotations

import logging

from core.services_core.db_state import get_readonly_db

logger = logging.getLogger(__name__)
_IN_CHUNK_SIZE = 500


def _chunks(items: list[int], size: int | None = None):
    size = _IN_CHUNK_SIZE if size is None else size
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _resolve_model_filter(
    con,
    model_scope: str,
    table_alias: str = "fwt",
) -> tuple[str, list[object]]:
    """Returns (sql_fragment, params) to append to WHERE clause.

    - "all" -> no filter
    - "active" -> filter by active model id; if active is None, no filter
    - "<model_id>" -> filter by explicit model id
    """
    if model_scope == "all":
        return "", []
    if model_scope == "active":
        from core.services_core.wd_active_model import (
            try_get_active_wd_model_id_for_legacy_schema,
        )

        model_id = try_get_active_wd_model_id_for_legacy_schema()
        if not model_id:
            return "", []
    else:
        model_id = model_scope

    from core.services_core.wd_dict_resolver import resolve_model_id_readonly

    mid = resolve_model_id_readonly(con, model_id)
    if mid is None:
        return " AND 0=1", []
    return f" AND {table_alias}.model_id = ?", [mid]


def build_caption(
    file_id: int,
    tag_exclude: list[str],
    base_model: str = "sdxl",
    model_scope: str = "active",
) -> str:
    """Build caption text for a single file.

    Args:
        file_id: Target file ID.
        tag_exclude: Tag names to exclude from caption.
        base_model: Model type (reserved for future tag vocabulary filtering).
        model_scope: WD-Tagger model scope ("active", "all", or model id).

    Returns:
        Comma-separated tag string, or empty string if no tags.
    """
    con = get_readonly_db()
    filter_sql, filter_params = _resolve_model_filter(con, model_scope)
    rows = con.execute(
        f"""SELECT td.tag_name
            FROM file_wd_tags fwt
            JOIN wd_tag_dict td ON td.id = fwt.tag_id
            WHERE fwt.file_id = ?{filter_sql}
            ORDER BY fwt.confidence_milli DESC""",
        (file_id, *filter_params),
    )

    exclude_set = set(t.lower().strip() for t in tag_exclude)
    tags = [
        row["tag_name"]
        for row in rows
        if row["tag_name"].lower().strip() not in exclude_set
    ]
    return ", ".join(tags)


def get_tag_summary(
    file_ids: list[int],
    limit: int = 200,
    model_scope: str = "active",
) -> list[dict]:
    """Get aggregated tag frequency across multiple files.

    Returns list of {tag_name, count, avg_confidence} sorted by count desc.
    """
    if not file_ids:
        return []

    con = get_readonly_db()
    filter_sql, filter_params = _resolve_model_filter(con, model_scope)
    by_tag: dict[str, tuple[int, float]] = {}
    for chunk in _chunks(list(dict.fromkeys(file_ids))):
        placeholders = ",".join("?" for _ in chunk)
        rows = con.execute(
            f"""SELECT td.tag_name,
                       COUNT(*) as count,
                       SUM(fwt.confidence_milli) / 1000.0 as confidence_sum
                FROM file_wd_tags fwt
                JOIN wd_tag_dict td ON td.id = fwt.tag_id
                WHERE fwt.file_id IN ({placeholders}){filter_sql}
                GROUP BY fwt.tag_id, td.tag_name""",
            (*chunk, *filter_params),
        )
        for row in rows:
            tag_name = row["tag_name"]
            count, confidence_sum = by_tag.get(tag_name, (0, 0.0))
            by_tag[tag_name] = (
                count + int(row["count"]),
                confidence_sum + float(row["confidence_sum"] or 0.0),
            )

    return [
        {
            "tag_name": tag_name,
            "count": count,
            "avg_confidence": round(confidence_sum / count, 4),
        }
        for tag_name, (count, confidence_sum) in sorted(
            by_tag.items(),
            key=lambda item: (-item[1][0], -(item[1][1] / item[1][0]), item[0]),
        )[:limit]
    ]
