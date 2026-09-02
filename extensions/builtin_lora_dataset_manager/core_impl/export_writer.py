"""Dataset export writer.

Creates kohya_ss-compatible folder structure with images and caption files.
Output: {output_base_dir}/{project_name}/{repeat}_{concept}/
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from core.services_core.db_state import get_readonly_db

from .caption_builder import _resolve_model_filter, build_caption
from .types import ExportResult

logger = logging.getLogger(__name__)

# Extension normalization for kohya_ss compatibility
_EXT_NORMALIZE = {
    ".jpeg": ".jpg",
}


def _resolve_file_path(file_id: int) -> str | None:
    """Get the filesystem path for a file_id."""
    con = get_readonly_db()
    row = con.execute(
        "SELECT path FROM files WHERE id = ? AND is_deleted = 0",
        (file_id,),
    ).fetchone()
    return row["path"] if row else None


def _has_wd_tags(file_id: int, model_scope: str = "active") -> bool:
    """Check if file has WD-Tagger tags."""
    con = get_readonly_db()
    filter_sql, filter_params = _resolve_model_filter(con, model_scope)
    row = con.execute(
        f"""SELECT 1
            FROM file_wd_tags fwt
            WHERE fwt.file_id = ?{filter_sql}
            LIMIT 1""",
        (file_id, *filter_params),
    ).fetchone()
    return row is not None


def export_dataset(
    project_id: int,
    project_name: str,
    concept: str,
    repeat: int,
    base_model: str,
    tag_exclude: list[str],
    file_ids: list[int],
    output_base_dir: str,
    model_scope: str = "active",
) -> ExportResult:
    """Export dataset to kohya_ss folder structure.

    Creates: {output_base_dir}/{project_name}/{repeat}_{concept}/
    Each image is copied with a matching .txt caption file.
    """
    result = ExportResult(project_id=project_id)

    # Build output directory (sanitize both name and concept to prevent traversal)
    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in project_name)
    safe_concept = "".join(c if c.isalnum() or c in "-_ " else "_" for c in concept)
    dataset_dir = os.path.join(output_base_dir, safe_name, f"{repeat}_{safe_concept}")

    # Final containment check after path construction
    real_dataset = os.path.realpath(dataset_dir)
    real_base = os.path.realpath(output_base_dir)
    if not (real_dataset == real_base
            or real_dataset.startswith(real_base + os.sep)):
        raise ValueError(
            f"Resolved dataset dir escapes output base: {real_dataset}"
        )

    os.makedirs(dataset_dir, exist_ok=True)
    result.output_dir = dataset_dir

    for file_id in file_ids:
        src_path = _resolve_file_path(file_id)
        if not src_path or not os.path.isfile(src_path):
            result.errors.append(f"file_id={file_id}: source file not found")
            result.skipped_count += 1
            continue

        if not _has_wd_tags(file_id, model_scope):
            result.errors.append(f"file_id={file_id}: no WD tags (skipped)")
            result.skipped_count += 1
            continue

        # Determine destination filename with extension normalization
        src_p = Path(src_path)
        ext = src_p.suffix.lower()
        ext = _EXT_NORMALIZE.get(ext, ext)
        dst_name = src_p.stem + ext
        dst_path = os.path.join(dataset_dir, dst_name)

        try:
            shutil.copy2(src_path, dst_path)
        except OSError as exc:
            result.errors.append(f"file_id={file_id}: copy failed: {exc}")
            result.skipped_count += 1
            continue

        # Build and write caption (skip empty captions by default)
        caption = build_caption(file_id, tag_exclude, base_model, model_scope)
        if caption:
            caption_path = os.path.join(dataset_dir, src_p.stem + ".txt")
            try:
                with open(caption_path, "w", encoding="utf-8") as f:
                    f.write(caption)
            except OSError as exc:
                result.errors.append(f"file_id={file_id}: caption write failed: {exc}")
                result.image_count += 1
                continue
        else:
            result.empty_caption_count += 1

        result.image_count += 1

    logger.info(
        "Export complete: project=%d, images=%d, skipped=%d, errors=%d",
        project_id, result.image_count, result.skipped_count, len(result.errors),
    )
    return result
