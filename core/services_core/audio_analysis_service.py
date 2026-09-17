"""Write helpers for audio analysis results."""

from __future__ import annotations


def save_transcription_analysis(file_id: int, engine_label: str, analysis_result) -> None:
    """Persist an audio transcription result into the analysis table."""
    from core.services_core.db_state import get_db

    db = get_db()

    ext_root = "extensions/builtin_analysis"
    import sys

    if ext_root not in sys.path:
        sys.path.insert(0, ext_root)

    from core_impl.store import save_analysis

    save_analysis(db, file_id, engine_label, analysis_result)
