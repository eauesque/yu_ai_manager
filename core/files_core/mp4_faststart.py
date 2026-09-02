"""MP4 faststart (moov atom relocation) utility.

When an MP4 file's moov atom comes after mdat, browsers cannot start
playback until the entire file is downloaded.
Moving the moov atom to the front (faststart) significantly speeds up
streaming playback start.

Uses ``-movflags +faststart`` when ffmpeg is available.
Skips when ffmpeg is not available (uses the original file as-is).
"""

import contextlib
import logging
import os
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Detect ffmpeg path once at module load time
_FFMPEG_PATH: str | None = shutil.which("ffmpeg")


def _needs_faststart(path: Path) -> bool:
    """Check if an MP4 file's moov atom comes after mdat.

    Returns True if moov comes after mdat (= faststart needed).
    Returns False on parse failure (processing skipped).
    """
    try:
        with open(path, "rb") as f:
            moov_offset = -1
            mdat_offset = -1
            offset = 0
            file_size = f.seek(0, 2)
            f.seek(0)

            while offset < file_size:
                f.seek(offset)
                header = f.read(8)
                if len(header) < 8:
                    break
                box_size, box_type = struct.unpack(">I4s", header)
                box_type_str = box_type.decode("ascii", errors="replace")

                if box_size == 0:
                    # box extends to end of file
                    box_size = file_size - offset
                elif box_size == 1:
                    # 64-bit extended size
                    ext = f.read(8)
                    if len(ext) < 8:
                        break
                    box_size = struct.unpack(">Q", ext)[0]

                if box_size < 8:
                    break

                if box_type_str == "moov":
                    moov_offset = offset
                elif box_type_str == "mdat":
                    mdat_offset = offset

                offset += box_size

            if moov_offset >= 0 and mdat_offset >= 0:
                return moov_offset > mdat_offset
    except (OSError, struct.error):
        pass
    return False


def ensure_faststart(cached_path: Path) -> bool:
    """Apply faststart to a cached MP4 file.

    Parameters
    ----------
    cached_path : Path
        Target MP4 file path (overwritten in-place)

    Returns
    -------
    bool
        True if faststart was applied, False if not needed or on failure
    """
    if not _FFMPEG_PATH:
        return False

    suffix = cached_path.suffix.lower()
    if suffix not in (".mp4", ".m4v", ".mov", ".m4a"):
        return False

    if not _needs_faststart(cached_path):
        return False

    logger.info("MP4 faststart 適用中: %s", cached_path.name)

    # Move moov atom to front via ffmpeg (codec copy, no re-encoding)
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix, dir=str(cached_path.parent))
    os.close(tmp_fd)
    try:
        result = subprocess.run(
            [
                _FFMPEG_PATH,
                "-i", str(cached_path),
                "-c", "copy",
                "-movflags", "+faststart",
                "-y",
                str(tmp_path),
            ],
            capture_output=True,
            timeout=30,  # 30s is sufficient for -c copy (no re-encoding)
        )
        if result.returncode != 0:
            logger.warning("ffmpeg faststart 失敗: %s", result.stderr[:200])
            _cleanup_tmp(tmp_path)
            return False

        # Replace original file
        os.replace(tmp_path, str(cached_path))
        logger.info("MP4 faststart 完了: %s", cached_path.name)
        return True
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning("ffmpeg faststart エラー: %s", e)
        _cleanup_tmp(tmp_path)
        return False


def _cleanup_tmp(tmp_path: str) -> None:
    with contextlib.suppress(OSError):
        os.unlink(tmp_path)
