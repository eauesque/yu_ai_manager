"""Extract audio track from media files using ffmpeg."""

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_FFMPEG_TIMEOUT = 120  # seconds

# Audio-only extensions (no extraction needed)
_AUDIO_EXTS = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".opus"}
# Video extensions (audio extraction needed)
_VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv", ".flv", ".ts"}


def is_audio_file(path: str) -> bool:
    return Path(path).suffix.lower() in _AUDIO_EXTS


def is_video_file(path: str) -> bool:
    return Path(path).suffix.lower() in _VIDEO_EXTS


def has_audio_track(path: str) -> bool:
    return is_audio_file(path) or is_video_file(path)


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def extract_audio(media_path: str, output_dir: str | None = None) -> Path | None:
    """Extract audio from media file as WAV (16kHz mono for Whisper).

    For audio files, converts to WAV format.
    For video files, extracts audio track and converts.

    Returns:
        Path to WAV file, or None on failure.
    """
    if not ffmpeg_available():
        logger.error("ffmpeg not found in PATH")
        return None

    src = Path(media_path)
    if not src.exists():
        logger.error("File not found: %s", media_path)
        return None

    if output_dir:
        out = Path(output_dir) / f"{src.stem}.wav"
    else:
        tmp = tempfile.mkdtemp(prefix="yu_audio_")
        out = Path(tmp) / f"{src.stem}.wav"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(src),
        "-vn",              # no video
        "-acodec", "pcm_s16le",
        "-ar", "16000",     # 16kHz for Whisper
        "-ac", "1",         # mono
        str(out),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_FFMPEG_TIMEOUT,
        )
        if result.returncode != 0:
            stderr = result.stderr[:300] if result.stderr else ""
            if "does not contain any stream" in stderr.lower():
                logger.warning("No audio track in %s", media_path)
                return None
            logger.error("ffmpeg failed (rc=%d): %s", result.returncode, stderr)
            return None

        if out.exists() and out.stat().st_size > 0:
            return out

        logger.error("ffmpeg produced empty output for %s", media_path)
        return None

    except subprocess.TimeoutExpired:
        logger.error("ffmpeg timeout (%ds) for %s", _FFMPEG_TIMEOUT, media_path)
        return None
    except FileNotFoundError:
        logger.error("ffmpeg not found")
        return None


def get_audio_duration(media_path: str) -> float | None:
    """Get audio duration in seconds using ffprobe."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None

    try:
        result = subprocess.run(
            [ffprobe, "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(media_path)],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError):
        pass
    return None
