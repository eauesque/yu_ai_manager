"""Video frame extraction and detection aggregation for YOLO.

Extracts frames at regular intervals using ffmpeg, runs YOLO detection
on each frame, and aggregates results across all frames.
"""

import json
import logging
import os
import subprocess
import tempfile
from contextlib import contextmanager, suppress

logger = logging.getLogger(__name__)


def get_video_duration_seconds(path: str) -> float | None:
    """Get video duration in seconds via ffprobe.

    Returns None if ffprobe fails or is unavailable.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                str(path),
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None
        info = json.loads(result.stdout)
        return float(info.get("format", {}).get("duration", 0))
    except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError, FileNotFoundError):
        return None


def extract_frames_for_detection(
    path: str,
    interval_sec: float = 2.0,
    max_frames: int = 30,
    target_size: int = 640,
) -> list[str]:
    """Extract frames from a video at regular intervals.

    Uses ffmpeg to extract frames scaled to target_size max dimension.

    Args:
        path: video file path
        interval_sec: seconds between frames
        max_frames: maximum number of frames
        target_size: scale longest edge to this

    Returns:
        List of temporary file paths (caller must clean up)
    """
    from core.files_core.media_video import check_ffmpeg
    if not check_ffmpeg():
        logger.warning("ffmpeg not available, skipping video frame extraction")
        return []

    duration = get_video_duration_seconds(path)
    if duration is None or duration < 0.1:
        logger.warning("Could not determine duration for %s", path)
        return []

    # Calculate frame timestamps
    timestamps = []
    t = 0.0
    while t < duration and len(timestamps) < max_frames:
        timestamps.append(t)
        t += interval_sec

    if not timestamps:
        return []

    tmp_dir = tempfile.mkdtemp(prefix="yolo_frames_")
    frame_paths = []

    for i, ts in enumerate(timestamps):
        out_path = os.path.join(tmp_dir, f"frame_{i:04d}.jpg")
        try:
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-ss", f"{ts:.2f}",
                    "-i", str(path),
                    "-vframes", "1",
                    "-vf", f"scale={target_size}:{target_size}:force_original_aspect_ratio=decrease",
                    "-pix_fmt", "yuvj420p",
                    "-y",
                    out_path,
                ],
                capture_output=True, timeout=10,
            )
            if result.returncode == 0 and os.path.exists(out_path):
                frame_paths.append(out_path)
        except subprocess.TimeoutExpired:
            logger.debug("ffmpeg timeout extracting frame at %.1fs from %s", ts, path)

    logger.debug("Extracted %d/%d frames from %s", len(frame_paths), len(timestamps), path)
    return frame_paths


def aggregate_video_detections(
    per_frame_detections: list[list[dict]],
) -> list[dict]:
    """Aggregate detections across multiple video frames.

    For each detected class, keeps the highest confidence and tracks
    in how many frames the class appeared.

    Args:
        per_frame_detections: list of detection lists, one per frame

    Returns:
        Aggregated detection list with frame_count and total_frames fields
    """
    total_frames = len(per_frame_detections)
    if total_frames == 0:
        return []

    # class_id -> {max_conf, best_bbox, frame_count}
    class_agg: dict[int, dict] = {}

    for detections in per_frame_detections:
        # Track unique classes per frame
        seen_in_frame: set = set()
        for det in detections:
            cid = det["class_id"]
            conf = det["confidence"]

            if cid not in class_agg:
                class_agg[cid] = {
                    "class_id": cid,
                    "class_name": det["class_name"],
                    "confidence": conf,
                    "bbox": det["bbox"],
                    "frame_count": 0,
                }

            entry = class_agg[cid]
            if conf > entry["confidence"]:
                entry["confidence"] = conf
                entry["bbox"] = det["bbox"]

            if cid not in seen_in_frame:
                entry["frame_count"] += 1
                seen_in_frame.add(cid)

    # Build result
    results = []
    for entry in class_agg.values():
        results.append({
            "class_id": entry["class_id"],
            "class_name": entry["class_name"],
            "confidence": round(entry["confidence"], 4),
            "bbox": entry["bbox"],
            "frame_count": entry["frame_count"],
            "total_frames": total_frames,
        })

    results.sort(key=lambda d: d["confidence"], reverse=True)
    return results


def cleanup_frames(frame_paths: list[str]) -> None:
    """Remove temporary frame files and their parent directory."""
    if not frame_paths:
        return
    parent = None
    for p in frame_paths:
        try:
            os.remove(p)
            if parent is None:
                parent = os.path.dirname(p)
        except OSError:
            pass
    if parent:
        with suppress(OSError):
            os.rmdir(parent)


@contextmanager
def video_detection_frames(
    path: str,
    interval_sec: float = 2.0,
    max_frames: int = 30,
    target_size: int = 640,
):
    """Context manager that extracts video frames for YOLO detection.

    TemporaryDirectory で自動クリーンアップを保証する。

    Usage::

        with video_detection_frames(path, target_size=640) as frame_paths:
            for fp in frame_paths:
                process(fp)
    """
    from core.files_core.media_video import check_ffmpeg
    if not check_ffmpeg():
        logger.warning("ffmpeg not available, skipping video frame extraction")
        yield []
        return

    duration = get_video_duration_seconds(path)
    if duration is None or duration < 0.1:
        logger.warning("Could not determine duration for %s", path)
        yield []
        return

    timestamps = []
    t = 0.0
    while t < duration and len(timestamps) < max_frames:
        timestamps.append(t)
        t += interval_sec

    if not timestamps:
        yield []
        return

    with tempfile.TemporaryDirectory(prefix="yolo_frames_") as tmp_dir:
        frame_paths: list[str] = []
        for i, ts in enumerate(timestamps):
            out_path = os.path.join(tmp_dir, f"frame_{i:04d}.jpg")
            try:
                result = subprocess.run(
                    [
                        "ffmpeg",
                        "-ss", f"{ts:.2f}",
                        "-i", str(path),
                        "-vframes", "1",
                        "-vf", f"scale={target_size}:{target_size}:force_original_aspect_ratio=decrease",
                        "-pix_fmt", "yuvj420p",
                        "-y",
                        out_path,
                    ],
                    capture_output=True, timeout=10,
                )
                if result.returncode == 0 and os.path.exists(out_path):
                    frame_paths.append(out_path)
            except subprocess.TimeoutExpired:
                logger.debug("ffmpeg timeout extracting frame at %.1fs from %s", ts, path)

        logger.debug("Extracted %d/%d frames from %s", len(frame_paths), len(timestamps), path)
        yield frame_paths
