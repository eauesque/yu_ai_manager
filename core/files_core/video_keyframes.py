"""Keyframe extraction from video files for content analysis.

Provides a shared module for WD-Tagger, CLIP indexer, and AI Analysis
to extract representative frames from video files using ffmpeg.

Strategies:
  - "uniform": evenly spaced across duration
  - "single": one frame at 25% position
  - "scene": ffmpeg scene change detection, fallback to uniform
"""

import functools
import logging
import re
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

logger = logging.getLogger(__name__)


@functools.cache
def _check_ffprobe() -> bool:
    return shutil.which("ffprobe") is not None


def get_video_duration_ms(video_path: str) -> int | None:
    """Get video duration in milliseconds using ffprobe.

    Returns None if ffprobe is unavailable or the duration cannot be read.
    """
    if not _check_ffprobe():
        return None
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            capture_output=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        raw = result.stdout.decode("utf-8", errors="ignore").strip()
        if not raw or raw == "N/A":
            return None
        return int(float(raw) * 1000)
    except (subprocess.TimeoutExpired, ValueError, OSError) as exc:
        logger.debug("ffprobe duration failed for %s: %s", video_path, exc)
        return None


def _extract_frame_for_analysis(
    video_path: str, output_path: Path, timestamp: str, timeout: int = 15,
) -> bool:
    """Extract a single frame at high quality (no resize) for analysis."""
    try:
        cmd = [
            "ffmpeg", "-ss", timestamp,
            "-i", str(video_path),
            "-vframes", "1",
            "-q:v", "2",  # JPEG quality ~95
            "-pix_fmt", "yuvj420p",
            "-y", str(output_path),
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
        )
        return result.returncode == 0 and output_path.exists()
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.debug("Frame extraction failed at %s: %s", timestamp, exc)
        return False


def _seconds_to_timestamp(seconds: float) -> str:
    """Convert seconds to HH:MM:SS.mmm timestamp."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def _detect_scene_changes(
    video_path: str,
    threshold: float = 0.4,
    max_scenes: int = 8,
    timeout: int = 30,
) -> list[float]:
    """Detect scene change timestamps using ffmpeg scene filter.

    Returns list of timestamps (seconds) where scene changes occur.
    Falls back to empty list on failure.
    """
    try:
        cmd = [
            "ffmpeg", "-i", str(video_path),
            "-vf", f"select='gt(scene,{threshold})',showinfo",
            "-f", "null", "-",
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
        )
        # showinfo prints pts_time in stderr
        stderr_text = result.stderr.decode("utf-8", errors="ignore")
        timestamps: list[float] = []
        for match in re.finditer(r"pts_time:\s*([\d.]+)", stderr_text):
            ts = float(match.group(1))
            timestamps.append(ts)
        # Limit to max_scenes, evenly sampling if too many
        if len(timestamps) > max_scenes:
            step = len(timestamps) / max_scenes
            timestamps = [timestamps[int(i * step)] for i in range(max_scenes)]
        return timestamps
    except (subprocess.TimeoutExpired, OSError, ValueError) as exc:
        logger.debug("Scene detection failed for %s: %s", video_path, exc)
        return []


def _extract_at_positions(
    video_path: str,
    output_dir: str,
    positions: list[float],
    timeout: int = 15,
) -> list[Path]:
    """Extract frames at specific second positions."""
    frames: list[Path] = []
    for idx, pos in enumerate(positions):
        ts = _seconds_to_timestamp(pos)
        out = Path(output_dir) / f"frame_{idx}.jpg"
        if _extract_frame_for_analysis(video_path, out, ts, timeout):
            frames.append(out)
        else:
            logger.debug("Failed to extract frame %d at %s", idx, ts)
    return frames


def extract_keyframes(
    video_path: str,
    output_dir: str,
    count: int = 4,
    strategy: str = "uniform",
    scene_threshold: float = 0.4,
    timeout: int = 15,
) -> list[Path]:
    """Extract keyframes from a video file.

    Args:
        video_path: Path to the video file.
        output_dir: Directory to write extracted JPEG frames.
        count: Number of frames to extract.
        strategy: 'uniform', 'scene', or 'single'.
        scene_threshold: Sensitivity for scene change detection (0.0-1.0).
        timeout: Per-frame ffmpeg timeout in seconds.

    Returns:
        List of Paths to extracted JPEG frames (may be empty on failure).
    """
    from .media_video import check_ffmpeg

    if not check_ffmpeg():
        logger.warning("ffmpeg not found; skipping video keyframe extraction")
        return []

    duration_ms = get_video_duration_ms(video_path)

    if strategy == "single":
        # Single frame at 25% position
        if duration_ms and duration_ms >= 1000:
            ts = _seconds_to_timestamp(duration_ms / 1000.0 * 0.25)
        else:
            ts = "00:00:00.000"
        out = Path(output_dir) / "frame_0.jpg"
        if _extract_frame_for_analysis(video_path, out, ts, timeout):
            return [out]
        return []

    if strategy == "scene":
        timestamps = _detect_scene_changes(
            video_path, scene_threshold, max_scenes=count, timeout=30,
        )
        if timestamps:
            return _extract_at_positions(video_path, output_dir, timestamps, timeout)
        # Fallback to uniform if no scenes detected
        logger.debug("No scene changes detected, falling back to uniform")

    # uniform strategy (also fallback for scene)
    if not duration_ms or duration_ms < 1000:
        out = Path(output_dir) / "frame_0.jpg"
        if _extract_frame_for_analysis(video_path, out, "00:00:00.000", timeout):
            return [out]
        return []

    duration_s = duration_ms / 1000.0
    positions = [duration_s * i / count for i in range(count)]
    return _extract_at_positions(video_path, output_dir, positions, timeout)


@contextmanager
def video_keyframes_context(
    video_path: str,
    count: int = 4,
    strategy: str = "uniform",
    scene_threshold: float = 0.4,
    timeout: int = 15,
):
    """Context manager that extracts keyframes into a temporary directory.

    Yields a list of Path objects for extracted frames.
    Cleans up the temporary directory on exit.

    Usage::

        with video_keyframes_context(path, count=4) as frames:
            for frame in frames:
                process(frame)
    """
    with TemporaryDirectory(prefix="yu_keyframes_") as tmpdir:
        frames = extract_keyframes(
            video_path, tmpdir, count, strategy, scene_threshold, timeout,
        )
        yield frames
