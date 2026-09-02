"""Shared filtering helpers for stats APIs."""


def ai_image_where(alias: str = "f") -> str:
    """Filter for AI-generated image files.

    Uses meta_source index (idx_files_deleted_source) instead of
    12× lower(path) LIKE which caused 24s+ full-table scans on 1.5M rows.
    meta_source already implies a valid image/video extension.
    """
    a = alias.strip() or "f"
    return f"""(
        {a}.is_deleted=0
        AND {a}.meta_source IS NOT NULL
        AND {a}.meta_source NOT IN ('', 'unknown', 'not_modified')
        AND {a}.meta_source NOT LIKE 'media_%'
    )"""

