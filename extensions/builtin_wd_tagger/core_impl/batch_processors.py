"""Batch processing helpers for WD-Tagger image and video files.

Separated from batch_ops.py to keep each module under 300 lines.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def process_image_batch(
    image_items, engine, pp, allow_nsfw, config,
    job, total, tagged, errors, processed_count, xmp_failed=0,
):
    """Process image files with tag_images_batch() for efficient GPU utilization.

    Returns ``(tagged, errors, processed_count, xmp_failed)``. ``xmp_failed``
    counts files where the DB tag write succeeded but XMP sidecar/embed
    write was rejected (read-only target, macOS bundle, decoder unable to
    rewrite, etc.) — these are NOT counted as ``errors`` because the tag
    record itself is intact.
    """
    from .store import save_wd_tags_batch
    from .xmp_write import write_xmp_to_file
    from .xmp_xml import build_xmp_packet

    batch_size = config.get("batch_inference_size", 8)

    for chunk_start in range(0, len(image_items), batch_size):
        if job.cancelled:
            job.complete_cancelled()
            return tagged, errors, processed_count, xmp_failed

        chunk = image_items[chunk_start:chunk_start + batch_size]
        filepaths = [fp for (_, _, fp) in chunk]

        # Batch inference
        try:
            batch_results = engine.tag_images_batch(filepaths, batch_size=batch_size)
        except Exception as exc:
            logger.warning("Batch inference failed, falling back to single: %s", exc)
            # Fallback: process one by one
            batch_results = []
            for fp in filepaths:
                try:
                    batch_results.append(engine.tag_image(fp))
                except Exception:
                    batch_results.append(None)

        pending_writes = []
        # Post-process and save each result
        for j, (_target_idx, fid, filepath) in enumerate(chunk):
            try:
                result = batch_results[j] if j < len(batch_results) else None
                if result is None:
                    errors += 1
                    processed_count += 1
                    _update_progress(job, processed_count, total, tagged, filepath)
                    continue

                result = pp.process(result, allow_nsfw=allow_nsfw)
                pending_writes.append((fid, result))

                # Write XMP
                if config.get("write_xmp", True):
                    tag_names = [t.tag for t in result.tags]
                    xmp_xml = build_xmp_packet(
                        tag_names=tag_names,
                        model=result.model,
                        general_threshold=config.get("general_threshold", 0.35),
                        character_threshold=config.get("character_threshold", 0.85),
                    )
                    if not write_xmp_to_file(filepath, xmp_xml):
                        xmp_failed += 1

                tagged += 1
            except Exception as exc:
                logger.warning("WD-Tagger error for file %s: %s", fid, exc)
                errors += 1

            processed_count += 1
            _update_progress(job, processed_count, total, tagged, filepath)

        if pending_writes:
            save_wd_tags_batch(pending_writes)

    return tagged, errors, processed_count, xmp_failed


def process_video_items(
    video_items, engine, pp, allow_nsfw, config,
    job, total, tagged, errors, processed_count, xmp_failed=0,
):
    """Process video files with keyframe extraction + individual inference."""
    from core.files_core.video_keyframes import video_keyframes_context
    from core.files_core.video_tag_merge import merge_wd_tag_results

    from .store import save_wd_tags_batch

    for _target_idx, fid, filepath in video_items:
        if job.cancelled:
            job.complete_cancelled()
            return tagged, errors, processed_count, xmp_failed

        try:
            from core.configuration.json_rw import load_config_json
            full_cfg = load_config_json(None)
            va_cfg = full_cfg.get("video_analysis", {})
            kf_count = va_cfg.get("keyframe_count", 4)
            strategy = va_cfg.get("strategy", "uniform")
            scene_th = va_cfg.get("scene_threshold", 0.4)
            store_per_kf = va_cfg.get("store_per_keyframe", False)
            with video_keyframes_context(
                filepath, count=kf_count, strategy=strategy,
                scene_threshold=scene_th,
            ) as frames:
                if not frames:
                    errors += 1
                    processed_count += 1
                    _update_progress(job, processed_count, total, tagged, filepath)
                    continue
                frame_results = [engine.tag_image(str(f)) for f in frames]
            result = merge_wd_tag_results(frame_results)
            if store_per_kf:
                from core.files_core.video_keyframe_store import save_keyframe_results
                kf_data = []
                for kidx, fr in enumerate(frame_results):
                    kf_data.append({
                        "keyframe_idx": kidx,
                        "timestamp_ms": 0,
                        "wd_tags": [{"tag": t.tag, "confidence": t.confidence,
                                     "category": t.category} for t in fr.tags],
                    })
                save_keyframe_results(fid, kf_data, model=result.model)

            result = pp.process(result, allow_nsfw=allow_nsfw)
            save_wd_tags_batch([(fid, result)])
            tagged += 1

        except Exception as exc:
            logger.warning("WD-Tagger error for video file %s: %s", fid, exc)
            errors += 1

        processed_count += 1
        _update_progress(job, processed_count, total, tagged, filepath)

    # Video path does not embed XMP (skipped in single_ops + here);
    # xmp_failed is passed through so the batch_ops aggregator stays uniform.
    return tagged, errors, processed_count, xmp_failed


def _update_progress(job, processed, total, tagged, filepath):
    """Update job progress."""
    detail = str(filepath) if filepath else ""
    job.progress(processed, total, detail)
    job.update(
        message=f"WD-Tagger: {processed}/{total} ({tagged} tagged)"
    )
