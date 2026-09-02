"""Write helpers for video analysis results."""

from __future__ import annotations


def save_video_analysis(file_id: int, engine_label: str, analysis_result) -> None:
    """Persist a video analysis result into the shared analysis table."""
    import sys

    from core.services_core.db_state import get_db

    db = get_db()
    ext_root = "extensions/builtin_analysis"
    if ext_root not in sys.path:
        sys.path.insert(0, ext_root)

    from core_impl.store import save_analysis

    save_analysis(db, file_id, engine_label, analysis_result)
