"""Video audio extraction helpers (ffmpeg).

Extracts audio from video files as WAV (mono, 16 kHz PCM s16le)
for use with S2T (speech-to-text) pipelines.
"""

import logging
import subprocess
import tempfile
from pathlib import Path

from core.files_core.media_video import check_ffmpeg

logger = logging.getLogger(__name__)

# Maximum ffmpeg timeout in seconds
_MAX_TIMEOUT = 120


def extract_audio_wav(
    video_path: str,
    output_path: str | None = None,
    sample_rate: int = 16000,
) -> str | None:
    """Extract audio from a video file as mono WAV.

    Args:
        video_path: Path to the source video file.
        output_path: Destination WAV path. If None, a temp file is created.
        sample_rate: Target sample rate (default 16000 for Whisper).

    Returns:
        Path to the WAV file on success, None on failure.
        If a temp file was created, the caller is responsible for cleanup.
    """
    if not check_ffmpeg():
        logger.error("ffmpeg not found in PATH")
        return None

    video = Path(video_path)
    if not video.is_file():
        logger.error("Video file not found: %s", video_path)
        return None

    # Create temp file if no output path given
    if output_path is None:
        tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115 — intentional: file lives beyond context
            suffix=".wav", prefix="yu_s2t_", delete=False,
        )
        output_path = tmp.name
        tmp.close()

    # Get video duration for timeout calculation
    timeout = _get_timeout(video_path)

    cmd = [
        "ffmpeg",
        "-i", str(video_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", str(sample_rate),
        "-ac", "1",
        "-y",
        str(output_path),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="ignore")
            logger.error("ffmpeg audio extraction failed (code %d): %s",
                         result.returncode, stderr[:200])
            return None
        # Verify output exists and has content
        out = Path(output_path)
        if not out.is_file() or out.stat().st_size < 100:
            logger.error("ffmpeg produced empty or missing output")
            return None
        return output_path
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg audio extraction timed out (%ds) for %s",
                      timeout, video_path)
        return None
    except Exception as exc:
        logger.error("ffmpeg audio extraction error: %s", exc)
        return None


def _get_timeout(video_path: str) -> int:
    """Estimate timeout based on video duration. Falls back to max."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
             str(video_path)],
            capture_output=True,
            timeout=10,
        )
        duration = float(result.stdout.decode().strip())
        # Allow 2x the video duration, clamped to max
        return min(int(duration * 2) + 10, _MAX_TIMEOUT)
    except Exception:
        return _MAX_TIMEOUT
