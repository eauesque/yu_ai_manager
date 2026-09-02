"""Video tooling helpers (ffmpeg)."""

import functools
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


@functools.cache
def check_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def extract_video_frame(video_path, output_path, timestamp: str = "00:00:00") -> bool:
    try:
        output_path = Path(output_path).absolute()
        cmd = [
            "ffmpeg",
            "-i",
            str(video_path),
            "-ss",
            timestamp,
            "-vframes",
            "1",
            "-vf",
            "scale=400:400:force_original_aspect_ratio=decrease",
            "-pix_fmt",
            "yuvj420p",
            "-y",
            str(output_path),
        ]
        logger.debug(f"ffmpeg command: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=10,
        )
        if result.returncode != 0:
            logger.error(f"ffmpeg failed with code {result.returncode}")
            logger.error(f"ffmpeg stderr: {result.stderr.decode('utf-8', errors='ignore')}")
            return False
        logger.debug(f"Video frame saved to: {output_path}")
        logger.debug(f"File exists: {output_path.exists()}")
        return True
    except subprocess.TimeoutExpired:
        logger.error(f"ffmpeg timeout for {video_path}")
        return False
    except Exception as e:
        logger.error(f"ffmpeg error: {e}", exc_info=True)
        return False
