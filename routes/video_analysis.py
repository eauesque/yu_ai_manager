"""Video Analysis config API routes."""

import contextlib
import logging
import threading

from quart import Blueprint, request

from core.infra_core.api_errors import api_error, api_result
from core.infra_core.simple_ttl_cache import SimpleTTLCache
from core.services_core.db_async import run_db_sync

bp = Blueprint("video_analysis", __name__)
logger = logging.getLogger(__name__)

# /api/video-analysis/status:
#   - 旧クエリの path LIKE '%.mp4' OR ... 7 連結 (3s) は file_ext index 引きで
#     <1ms に解消済 (v4.134 系)。
#   - 残り cold-miss コストはワーカースレッドの DB 接続セットアップ + 初回 import で
#     prod 観測 258ms。書き込み path がほぼ無い (ffmpeg presence と video count は
#     ほとんど変動しない) ので TTL を 300 秒に拡大、起動時 warm-up daemon を追加。
#   - STATUS_API_PERF_PATTERN.md § Layer 2 パターン適用。
_VA_STATUS_CACHE = SimpleTTLCache(ttl_seconds=300.0)

_va_status_warmup_started = False
_va_status_warmup_lock = threading.Lock()


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


@bp.route("/api/video-analysis/config", methods=["GET"])
async def api_va_config_get():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    from core.files_core.video_config_ops import get_video_config
    return api_result({"config": await run_db_sync(get_video_config)})


@bp.route("/api/video-analysis/config", methods=["POST"])
async def api_va_config_save():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    data = await request.get_json(silent=True)
    if not isinstance(data, dict):
        return api_error("JSON object required", 400, code="invalid_json")
    try:
        from core.files_core.video_config_ops import save_video_config
        saved = await run_db_sync(save_video_config, data)
        return api_result({"config": saved})
    except ValueError:
        logger.exception("Failed to save video analysis config")
        return api_error("Invalid video analysis config", 400, code="invalid_value")


@bp.route("/api/video-analysis/status", methods=["GET"])
async def api_va_status():
    """Return video analysis status info (ffmpeg availability, counts)."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    def _fetch():
        from core.files_core.media_video import check_ffmpeg
        from core.services_core.db_state import get_readonly_db

        has_ffmpeg = check_ffmpeg()
        con = get_readonly_db()
        # idx_files_deleted_ext (is_deleted, file_ext) で 1 ext あたり O(log N)
        # の seek。LIKE 7 連結のフルスキャン (3.1 秒) を index 引きに置き換え。
        video_count = con.execute(
            "SELECT COUNT(*) FROM files WHERE is_deleted=0 "
            "AND file_ext IN ('.mp4','.webm','.avi','.mov','.mkv','.m4v','.ogv')"
        ).fetchone()[0]

        keyframe_count = 0
        with contextlib.suppress(Exception):  # table may not exist yet
            keyframe_count = con.execute(
                "SELECT COUNT(DISTINCT file_id) FROM file_keyframes"
            ).fetchone()[0]

        return {
            "ffmpeg": has_ffmpeg,
            "video_files": video_count,
            "files_with_keyframes": keyframe_count,
        }

    cached = _VA_STATUS_CACHE.peek("payload")
    if cached is not None:
        return api_result(cached)
    result = await run_db_sync(_fetch)
    _VA_STATUS_CACHE.put("payload", result)
    return api_result(result)


def _warmup_va_status_cache() -> None:
    """Best-effort cold-start warm-up so the first /api/video-analysis/status
    poll doesn't pay the cold-worker DB connection setup cost."""
    try:
        from core.files_core.media_video import check_ffmpeg
        from core.services_core.db_state import get_readonly_db

        has_ffmpeg = check_ffmpeg()
        con = get_readonly_db()
        video_count = con.execute(
            "SELECT COUNT(*) FROM files WHERE is_deleted=0 "
            "AND file_ext IN ('.mp4','.webm','.avi','.mov','.mkv','.m4v','.ogv')"
        ).fetchone()[0]
        keyframe_count = 0
        with contextlib.suppress(Exception):
            keyframe_count = con.execute(
                "SELECT COUNT(DISTINCT file_id) FROM file_keyframes"
            ).fetchone()[0]
        _VA_STATUS_CACHE.put("payload", {
            "ffmpeg": has_ffmpeg,
            "video_files": video_count,
            "files_with_keyframes": keyframe_count,
        })
    except Exception:
        logger.debug("video-analysis status warm-up skipped", exc_info=True)


def ensure_va_status_warmup() -> None:
    """Idempotently kick off a daemon thread that primes _VA_STATUS_CACHE."""
    global _va_status_warmup_started
    with _va_status_warmup_lock:
        if _va_status_warmup_started:
            return
        _va_status_warmup_started = True
    threading.Thread(
        target=_warmup_va_status_cache,
        daemon=True,
        name="va-status-warmup",
    ).start()


# Kick off on Blueprint import (matches the wd-tagger stats pattern).
ensure_va_status_warmup()
