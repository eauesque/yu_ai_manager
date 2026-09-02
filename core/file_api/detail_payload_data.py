"""Data access helpers for file detail payloads."""

import contextlib
from typing import Any

from core.files_core.animated_detect import is_animated_image

FILE_DETAIL_SQL = (
    "SELECT f.*, tm.raw_prompt, tm.raw_negative, tm.format, tm.raw_meta_json, tm.model_name, tm.model_hash, "
    "tm.prompt_lang, tm.prompt_lang_confidence "
    "FROM files f "
    "LEFT JOIN templates tm ON tm.file_id=f.id "
    "WHERE f.id=?"
)

FILE_TAGS_SQL = """SELECT t.tag, t.namespace, ft.weight, ft.source
   FROM file_tags ft
   JOIN tags t ON t.id=ft.tag_id
   WHERE ft.file_id=?
   ORDER BY t.namespace, t.tag"""


def fetch_file_row(con, file_id: int):
    return con.execute(FILE_DETAIL_SQL, (file_id,)).fetchone()


def fetch_tag_list(con, file_id: int) -> list[dict[str, Any]]:
    tags = con.execute(FILE_TAGS_SQL, (file_id,))
    return [{"tag": row[0], "namespace": row[1], "weight": row[2], "source": row[3]} for row in tags]


def _detect_animated(path: str) -> bool | None:
    """Detect animation for regular files (not ZIP members)."""
    if "!" in path:
        return None  # ZIP members: can't read directly
    return is_animated_image(path)


def build_base_result(file_row, parsed_fields: dict[str, Any], tag_list: list[dict[str, Any]], raw_meta_json: str) -> dict[str, Any]:
    path = file_row["path"]
    animated = _detect_animated(path)
    result: dict[str, Any] = {
        "id": file_row["id"],
        "path": path,
        "mtime": file_row["mtime"],
        "size": file_row["size"],
        "meta_source": file_row["meta_source"],
        "positive": parsed_fields["positive"],
        "negative": parsed_fields["negative"],
        "format": file_row["format"],
        "resolution": parsed_fields["resolution"],
        "model": parsed_fields["model"],
        "parameters": parsed_fields["parameters"],
        "tags": tag_list,
        "raw_meta_json": raw_meta_json,
    }
    if animated is not None:
        result["is_animated"] = animated
    with contextlib.suppress(IndexError, KeyError):
        result["has_sweep"] = bool(file_row["has_sweep"])
    # Language detection result (migration 45)
    try:
        prompt_lang = file_row["prompt_lang"]
        if prompt_lang:
            result["prompt_lang"] = prompt_lang
            result["prompt_lang_confidence"] = file_row["prompt_lang_confidence"] or 0.0
    except (IndexError, KeyError):
        pass
    return result
