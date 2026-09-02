"""Single-file WD-Tagger operations.

Tag one file: validate -> infer -> save to DB -> optionally write XMP.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def tag_one_file(file_id: int, force: bool = False) -> dict:
    """Run WD-Tagger on a single file.

    Args:
        file_id: Database file ID
        force: If True, re-tag even if tags already exist

    Returns:
        dict with tag results or error info
    """
    from core.files_core.media_types import is_taggable_file, is_video_file
    from core.files_core.video_keyframes import video_keyframes_context
    from core.files_core.video_tag_merge import merge_wd_tag_results
    from core.services_core.wd_tagger_query_service import get_active_file_record

    from .config_ops import get_config
    from .engine_factory import get_engine
    from .store import get_wd_tags, save_wd_tags
    from .xmp_write import write_xmp_to_file
    from .xmp_xml import build_xmp_packet

    # Validate file exists and is not deleted
    row = get_active_file_record(file_id)
    if not row:
        return {"error": "File not found or deleted", "code": "file_not_found"}

    filepath = row["path"]
    meta_source = row["meta_source"]

    # Check if file exists on disk
    if not Path(filepath).exists():
        return {"error": "File not found on disk", "code": "file_missing"}

    # Skip non-taggable files (audio, PDF, etc.)
    if not is_taggable_file(filepath):
        return {"error": "File type not supported for tagging", "code": "unsupported_type"}

    # Check if already tagged (unless force)
    if not force:
        existing = get_wd_tags(file_id)
        if existing:
            return {
                "skipped": True,
                "reason": "already_tagged",
                "tag_count": len(existing),
            }

    # Get config and engine
    config = get_config()
    engine = get_engine(config)

    if not engine.is_available():
        return {"error": "Model not downloaded", "code": "model_not_available"}

    # Run inference (video: extract keyframes, tag each, merge)
    is_video = is_video_file(filepath)
    if is_video:
        from core.configuration.json_rw import load_config_json
        full_cfg = load_config_json(None)
        va_cfg = full_cfg.get("video_analysis", {})
        kf_count = va_cfg.get("keyframe_count", 4)
        strategy = va_cfg.get("strategy", "uniform")
        scene_th = va_cfg.get("scene_threshold", 0.4)
        store_per_kf = va_cfg.get("store_per_keyframe", False)
        with video_keyframes_context(
            filepath, count=kf_count, strategy=strategy, scene_threshold=scene_th,
        ) as frames:
            if not frames:
                return {"error": "Failed to extract keyframes", "code": "keyframe_error"}
            frame_results = [engine.tag_image(str(f)) for f in frames]
        result = merge_wd_tag_results(frame_results)
        if store_per_kf:
            from core.files_core.video_keyframe_store import save_keyframe_results
            kf_data = []
            for idx, fr in enumerate(frame_results):
                kf_data.append({
                    "keyframe_idx": idx,
                    "timestamp_ms": 0,
                    "wd_tags": [{"tag": t.tag, "confidence": t.confidence,
                                 "category": t.category} for t in fr.tags],
                })
            save_keyframe_results(file_id, kf_data, model=result.model)
    else:
        result = engine.tag_image(filepath)

    # Post-processing: normalize + NSFW filter
    from .tag_postprocess import TagPostProcessor
    pp = TagPostProcessor()
    result = pp.process(result, allow_nsfw=not config.get("nsfw_filter", False))

    tag_count = save_wd_tags(file_id, result)

    # Optionally write XMP (skip for video files)
    xmp_written = False
    if not is_video and config.get("write_xmp", True):
        tag_names = [t.tag for t in result.tags]
        xmp_xml = build_xmp_packet(
            tag_names=tag_names,
            model=result.model,
            general_threshold=config.get("general_threshold", 0.35),
            character_threshold=config.get("character_threshold", 0.85),
        )
        xmp_written = write_xmp_to_file(filepath, xmp_xml)

    logger.info(
        "Tagged file %d: %d tags, rating=%s, xmp=%s%s",
        file_id, tag_count, result.rating, xmp_written,
        " (video)" if is_video else "",
    )

    return {
        "file_id": file_id,
        "filepath": filepath,
        "meta_source": meta_source,
        "tag_count": tag_count,
        "rating": result.rating,
        "xmp_written": xmp_written,
        "tags": result.to_dict()["tags"],
    }
