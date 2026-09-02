"""MP4 faststart pre-processing after scan completion.

After scanning, checks moov atom positions of all MP4/MOV files in a background
thread, and pre-creates copies in cache/faststart/ for non-faststart files.
This completely eliminates ffmpeg processing delay (0.5-2s) on first playback.
"""

import logging
import threading
from pathlib import Path

from core.services_core.db_api import get_readonly_db

logger = logging.getLogger(__name__)

_FASTSTART_EXTS = frozenset({".mp4", ".m4v", ".mov", ".m4a"})
_running = False
_lock = threading.Lock()


def start_faststart_prescan() -> bool:
    """Start faststart pre-processing in the background.

    Skips if already running. Returns whether it was started.
    """
    global _running
    with _lock:
        if _running:
            logger.debug("[faststart-prescan] 既に実行中 — スキップ")
            return False
        _running = True

    threading.Thread(
        target=_prescan_worker,
        name="faststart-prescan",
        daemon=True,
    ).start()
    return True


def _prescan_worker() -> None:
    """Pre-create faststart cache for all MP4/MOV files."""
    global _running
    try:
        _do_prescan()
    except Exception as exc:
        logger.warning("[faststart-prescan] エラー: %s", exc)
    finally:
        with _lock:
            _running = False


def _do_prescan() -> None:
    from .mp4_faststart import _FFMPEG_PATH, _needs_faststart
    from .plain_faststart_cache import (
        MAX_FILE_BYTES,
        _cache_key,
        _ensure_cache_dir,
    )

    if not _FFMPEG_PATH:
        logger.debug("[faststart-prescan] ffmpeg が見つからないためスキップ")
        return

    # Fetch only MP4/MOV files from DB (not all 150K+ files)
    con = get_readonly_db()
    # Use LIKE filters on path extension to avoid fetching all rows.
    # The "!" exclusion filters out archive members.
    ext_clauses = " OR ".join(
        f"LOWER(path) LIKE '%{ext}'" for ext in _FASTSTART_EXTS
    )
    candidates = con.execute(
        f"SELECT id, path FROM files WHERE is_deleted = 0"
        f" AND path NOT LIKE '%!%'"
        f" AND ({ext_clauses})"
    )

    cache_dir = _ensure_cache_dir()
    seen = 0
    processed = 0
    skipped = 0
    cached = 0
    errors = 0

    for row in candidates:
        seen += 1
        path_str = row["path"]
        file_path = Path(path_str)
        try:
            if not file_path.exists():
                skipped += 1
                continue

            st = file_path.stat()

            # File size limit check
            if st.st_size > MAX_FILE_BYTES:
                skipped += 1
                continue

            # Cache hit check
            key = _cache_key(str(file_path), st.st_mtime, st.st_size)
            suffix = file_path.suffix.lower()
            cached_path = cache_dir / f"{key}{suffix}"
            if cached_path.exists() and cached_path.stat().st_size > 0:
                cached += 1
                continue

            # Check moov position (fast: reads only a few header bytes)
            if not _needs_faststart(file_path):
                skipped += 1  # Already faststarted
                continue

            # Create faststart cache
            _create_faststart_cache(file_path, cached_path, suffix)
            processed += 1

        except Exception as exc:
            errors += 1
            logger.debug("[faststart-prescan] %s: %s", file_path.name, exc)

    if seen == 0:
        logger.debug("[faststart-prescan] 対象ファイルなし")
        return

    logger.info(
        "[faststart-prescan] 完了: %d 件検査, %d 件処理, %d 件キャッシュ済み, %d 件スキップ, %d 件エラー",
        seen, processed, cached, skipped, errors,
    )

    # Capacity check
    if processed > 0:
        from .plain_faststart_cache import _evict_if_needed
        _evict_if_needed()


def _create_faststart_cache(file_path: Path, cached_path: Path, suffix: str) -> None:
    """Create faststart cache via ffmpeg."""
    import os
    import subprocess
    import tempfile

    from .mp4_faststart import _FFMPEG_PATH

    cache_dir = cached_path.parent
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix, dir=str(cache_dir))
    os.close(tmp_fd)

    try:
        result = subprocess.run(
            [
                _FFMPEG_PATH,
                "-i", str(file_path),
                "-c", "copy",
                "-movflags", "+faststart",
                "-y",
                str(tmp_path),
            ],
            capture_output=True,
            timeout=60,
        )
        if result.returncode != 0:
            logger.debug("[faststart-prescan] ffmpeg 失敗: %s — %s",
                         file_path.name, result.stderr[:200])
            _cleanup(tmp_path)
            return

        os.replace(tmp_path, str(cached_path))
        logger.debug("[faststart-prescan] キャッシュ作成: %s (%d MB)",
                     file_path.name, file_path.stat().st_size // (1024 * 1024))
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.debug("[faststart-prescan] エラー: %s — %s", file_path.name, exc)
        _cleanup(tmp_path)


def _cleanup(tmp_path: str) -> None:
    try:
        import os
        os.unlink(tmp_path)
    except OSError:
        pass
