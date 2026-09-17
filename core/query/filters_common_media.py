"""Model/media/tag SQL filter builders for query module."""

import re
from typing import Any

from .fts_like_helpers import trigram_match_phrase

# Extension sets for file_ext IN (...) queries (indexed via idx_files_deleted_ext)
_IMAGE_EXTS = (
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp",
    ".tif", ".tiff", ".avif", ".heif", ".heic", ".jxl", ".svg",
)
_VIDEO_EXTS = (
    ".webm", ".mp4", ".mov", ".m4v", ".avi", ".mkv",
    ".ogv", ".ts", ".m2ts",
)
_AUDIO_EXTS = (
    ".mp3", ".wav", ".ogg", ".opus", ".m4a", ".aac", ".flac",
)

# Cached flag: whether file_ext column exists (checked once)
_file_ext_available: bool | None = None


def _has_file_ext_column() -> bool:
    """Check if file_ext generated column is available (migration 50+)."""
    global _file_ext_available
    if _file_ext_available is not None:
        return _file_ext_available
    try:
        from core.services_core.db_api import get_readonly_db
        con = get_readonly_db()
        rows = con.execute("PRAGMA table_xinfo(files)").fetchall()
        _file_ext_available = any(r[1] == "file_ext" for r in rows)
    except Exception:
        _file_ext_available = False
    return _file_ext_available


def _ext_in_clause(exts: tuple) -> str:
    """Build optimized extension filter clause.

    Uses indexed file_ext column if available (migration 50+),
    falls back to LIKE chains for older schemas.
    """
    if _has_file_ext_column():
        placeholders = ", ".join(f"'{e}'" for e in exts)
        return f"f.file_ext IN ({placeholders})"
    # Fallback: legacy LIKE chains
    likes = " OR ".join(f"lower(f.path) LIKE '%{e}'" for e in exts)
    return f"({likes})"


def _ext_eq(ext: str) -> str:
    """Build single extension equality check."""
    if _has_file_ext_column():
        return f"f.file_ext = '{ext}'"
    return f"lower(f.path) LIKE '%{ext}'"


def _ext_in_list(exts: list) -> str:
    """Build multi-extension IN/OR check."""
    if _has_file_ext_column():
        placeholders = ", ".join(f"'{e}'" for e in exts)
        return f"f.file_ext IN ({placeholders})"
    likes = " OR ".join(f"lower(f.path) LIKE '%{e}'" for e in exts)
    return f"({likes})"


def apply_artist_filter(
    where_parts: list[str],
    params: list[Any],
    artist: str | None,
    con=None,
):
    if not (artist and artist.strip()):
        return
    artist_val = artist.strip()
    # Strip leading @ so "@name" and "name" are equivalent input forms.
    if artist_val.startswith("@"):
        artist_val = artist_val[1:].strip()
    if not artist_val:
        return
    base = artist_val
    at_tag = "@" + base
    # Resolve tag_id(s) upfront so the EXISTS uses a covering index on
    # file_tags(file_id, tag_id) without joining the tags table per row.
    if con is not None:
        rows = con.execute(
            "SELECT id FROM tags WHERE (namespace='artist' AND LOWER(tag)=LOWER(?)) "
            "OR ((namespace IS NULL OR namespace='') AND LOWER(tag)=LOWER(?))",
            (base, at_tag),
        ).fetchall()
        if rows:
            ids = [r[0] for r in rows]
            placeholders = ", ".join("?" * len(ids))
            where_parts.append(
                f"EXISTS(SELECT 1 FROM file_tags WHERE file_id=f.id AND tag_id IN ({placeholders}))"
            )
            params.extend(ids)
            return
        # Tag not found — query will return 0 rows; use FALSE-equivalent
        where_parts.append("0")
        return
    # Fallback when no connection is available — match both namespace='artist'
    # rows and raw '@name' tag rows (for images ingested before re-scan).
    where_parts.append(
        "EXISTS(SELECT 1 FROM file_tags ft JOIN tags t ON t.id=ft.tag_id "
        "WHERE ft.file_id=f.id "
        "AND ((t.namespace='artist' AND LOWER(t.tag)=LOWER(?)) "
        "OR ((t.namespace IS NULL OR t.namespace='') AND LOWER(t.tag)=LOWER(?))))"
    )
    params.append(base)
    params.append(at_tag)


def apply_file_format_filter(where_parts: list[str], file_format: str | None, format_exts: str | None = None):
    ff = "all" if not file_format or file_format == "all" else (file_format or "").lower()

    # Use indexed file_ext column if available (migration 50+),
    # otherwise fall back to LIKE chains via helper functions
    if ff == "image":
        where_parts.append(_ext_in_clause(_IMAGE_EXTS))
    elif ff == "video":
        where_parts.append(
            "(" + _ext_in_clause(_VIDEO_EXTS)
            + " OR f.meta_source LIKE '%webm%' OR f.meta_source LIKE 'media_video_%')"
        )
    elif ff == "audio":
        where_parts.append(
            "(" + _ext_in_clause(_AUDIO_EXTS)
            + " OR f.meta_source LIKE 'media_audio_%')"
        )
    elif ff == "webm":
        where_parts.append("(" + _ext_eq(".webm") + " OR f.meta_source LIKE '%webm%')")
    elif ff == "mp4":
        where_parts.append(_ext_eq(".mp4"))
    elif ff == "gif":
        where_parts.append(_ext_eq(".gif"))
    elif ff == "zip_member":
        where_parts.append("(f.path LIKE '%.zip!%' OR f.path LIKE '%.7z!%')")
    elif ff == "png":
        where_parts.append("(" + _ext_eq(".png") + " OR f.meta_source LIKE '%png%')")
    elif ff == "webp":
        where_parts.append("(" + _ext_eq(".webp") + " OR f.meta_source LIKE '%webp%')")
    elif ff in ("jpg", "jpeg"):
        where_parts.append(_ext_in_list([".jpg", ".jpeg"]))
    elif ff == "avif":
        where_parts.append(_ext_eq(".avif"))
    elif ff == "jxl":
        where_parts.append(_ext_eq(".jxl"))
    elif ff in ("heif", "heic"):
        where_parts.append(_ext_in_list([".heif", ".heic"]))
    elif ff == "svg":
        where_parts.append(_ext_eq(".svg"))

    if format_exts:
        exts = [
            ext
            for ext in [s.strip().lower() for s in str(format_exts).split(",")]
            if re.fullmatch(r"[a-z0-9]{1,8}", ext)
        ]
        if exts:
            exts = list(dict.fromkeys(exts))
            ext_terms = []
            for ext in exts:
                if ext == "zip":
                    ext_terms.append("f.path LIKE '%.zip!%'")
                elif ext == "7z":
                    ext_terms.append("f.path LIKE '%.7z!%'")
                else:
                    ext_terms.append(_ext_eq(f".{ext}"))
            where_parts.append("(" + " OR ".join(ext_terms) + ")")


def apply_model_filter(where_parts: list[str], model_filter: str | None):
    if not model_filter or model_filter == "all":
        return
    model_conditions = []
    filters = [f.strip() for f in model_filter.split(",") if f.strip()]
    for mf in filters:
        if mf == "sd":
            model_conditions.append("(f.meta_source LIKE '%a1111%' OR f.meta_source LIKE '%forge%')")
        elif mf == "nai":
            model_conditions.append("f.meta_source LIKE '%novel%'")
        elif mf == "comfy":
            model_conditions.append("f.meta_source LIKE '%comfy%'")
        elif mf == "tensor":
            model_conditions.append("f.meta_source LIKE '%tensor%'")
        elif mf == "unknown":
            model_conditions.append("(f.meta_source IS NULL OR f.meta_source = '')")
    if model_conditions:
        where_parts.append(f"({' OR '.join(model_conditions)})")


def apply_checkpoint_filter(where_parts: list[str], params: list[Any], checkpoint_filter: str | None):
    if not (checkpoint_filter and checkpoint_filter.strip()):
        return
    term = checkpoint_filter.strip().lower()
    search_term = f"%{term}%"

    # Branch A (fast, correlated EXISTS): templates with a populated
    # model_name. Per-file cost is one `templates.file_id` UNIQUE index lookup
    # plus LIKE on model_name/model_hash. Kept correlated so the planner can
    # walk `idx_files_deleted_mtime` DESC and short-circuit on the first LIMIT
    # rows -- this is the path that returned `novelai`-style abundant-match
    # queries in <1ms.
    # Branch B (FTS, materialised IN-list): templates with model_name IS NULL.
    # Replaces the previous correlated `raw_meta_json` LIKE with a single
    # `templates_fts` trigram MATCH that yields file ids whose raw_prompt
    # contains "model: <term>"; the outer per-file check is then an INTEGER PK
    # probe instead of a full JSON scan.
    # Trade-off: NAI-only files where the model name lives only in
    # raw_meta_json (not raw_prompt) fall out of both branches. Recovery is
    # to populate `templates.model_name` at scan time so they re-enter
    # Branch A.
    phrase = trigram_match_phrase(f"model: {term}")
    if phrase is not None:
        where_parts.append(
            "(EXISTS(SELECT 1 FROM templates tm2 WHERE tm2.file_id=f.id "
            "AND tm2.model_name IS NOT NULL "
            "AND (lower(tm2.model_name) LIKE ? OR lower(tm2.model_hash) LIKE ?))"
            " OR f.id IN ("
            "SELECT tm2.file_id FROM templates_fts tf2 "
            "JOIN templates tm2 ON tm2.id = tf2.rowid "
            "WHERE tm2.model_name IS NULL AND tf2.raw_prompt MATCH ?"
            "))"
        )
        params.append(search_term)
        params.append(search_term)
        params.append(phrase)
    else:
        # Term too short for trigram (<3 chars after the "model: " prefix is
        # always >=3, so this branch is effectively unreachable for non-empty
        # input -- kept as a defensive fallback that drops the JSON scan).
        where_parts.append(
            "(EXISTS(SELECT 1 FROM templates tm2 WHERE tm2.file_id=f.id "
            "AND tm2.model_name IS NOT NULL "
            "AND (lower(tm2.model_name) LIKE ? OR lower(tm2.model_hash) LIKE ?))"
            " OR EXISTS(SELECT 1 FROM templates tm2 WHERE tm2.file_id=f.id "
            "AND tm2.model_name IS NULL AND lower(tm2.raw_prompt) LIKE ?))"
        )
        params.append(search_term)
        params.append(search_term)
        params.append(f"%model: {term}%")


def apply_resolution_filter(
    where_parts: list[str],
    params: list[Any],
    min_width: int | None,
    max_width: int | None,
    min_height: int | None,
    max_height: int | None,
):
    if min_width is not None:
        where_parts.append("f.width >= ?")
        params.append(min_width)
    if max_width is not None:
        where_parts.append("f.width <= ?")
        params.append(max_width)
    if min_height is not None:
        where_parts.append("f.height >= ?")
        params.append(min_height)
    if max_height is not None:
        where_parts.append("f.height <= ?")
        params.append(max_height)
