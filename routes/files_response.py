"""Response helpers for file serving (ETag, Range, streaming, X-Accel-Redirect)."""

import os
from pathlib import Path

from quart import make_response, request, send_file

from core.files_core.response_types import FileError, FilePath, FileResult

# MIME types that require HTTP Range support (206 Partial Content) for
# proper seeking and streaming.  send_file handles Range automatically.
_STREAMABLE_MIMES = frozenset({
    "video/webm", "video/mp4", "video/quicktime", "video/x-m4v",
    "video/ogg", "video/x-msvideo", "video/x-matroska",
    "audio/mpeg", "audio/wav", "audio/ogg", "audio/mp4",
    "audio/aac", "audio/flac",
})

# -- X-Accel-Redirect (Nginx) / X-Sendfile (Apache/Caddy) support --
# Set YU_ACCEL_REDIRECT_PREFIX to enable reverse-proxy direct serving.
# Example: YU_ACCEL_REDIRECT_PREFIX=/internal-thumbs
# Nginx config: location /internal-thumbs/ { internal; alias /path/to/cache/thumbnails/; }
_ACCEL_PREFIX = os.environ.get("YU_ACCEL_REDIRECT_PREFIX", "").rstrip("/")
# Which header to use: "X-Accel-Redirect" (nginx) or "X-Sendfile" (apache/caddy)
_ACCEL_HEADER = os.environ.get("YU_ACCEL_HEADER", "X-Accel-Redirect")


def _cache_base() -> str:
    """Return absolute path of the thumbnail cache root as a string.

    Resolved lazily via core.paths so that Tauri / portable installs pick up
    the correct writable cache directory instead of a CWD-relative snapshot.
    """
    from core.paths import cache_path
    return str(cache_path("thumbnails").resolve())


def _try_accel_response(result: FilePath):
    """Build X-Accel-Redirect response if configured and path is inside cache dir.

    Returns None if accel is not configured or path is outside cache.
    """
    if not _ACCEL_PREFIX:
        return None
    try:
        cache_base = Path(_cache_base()).resolve()
        real_path = Path(result.path).resolve()
        try:
            rel_path = real_path.relative_to(cache_base)
        except ValueError:
            return None
        # Normalize to forward slashes for URL path
        rel = rel_path.as_posix()
        accel_uri = f"{_ACCEL_PREFIX}/{rel}" if rel else _ACCEL_PREFIX
        return accel_uri
    except Exception:
        return None


async def to_flask_response(result: FileResult, *, streamable: bool = False):
    """Convert a framework-neutral FileResult to a Quart response.

    Parameters
    ----------
    streamable:
        True for original media endpoints where HTTP Range (206) support
        is required.  When True, always delegates to ``send_file`` so
        that browsers can seek within video/audio files.
    """
    if isinstance(result, FileError):
        return result.message, result.status_code

    # Delegate video/audio files to send_file directly for Range request support
    if streamable and isinstance(result, FilePath) and result.mime_type in _STREAMABLE_MIMES:
        return await _streamable_response(result)

    # ETag / 304 handling (request.headers dependency stays in route layer)
    if result.etag:
        if_none_match = request.headers.get("If-None-Match")
        if if_none_match and if_none_match == result.etag:
            resp = await make_response("", 304)
            resp.headers["ETag"] = result.etag
            return resp

    if isinstance(result, FilePath):
        # P3: Try X-Accel-Redirect for reverse proxy direct serving
        accel_uri = _try_accel_response(result)
        if accel_uri:
            resp = await make_response("")
            resp.headers[_ACCEL_HEADER] = accel_uri
            resp.headers["Content-Type"] = result.mime_type
            if result.etag:
                resp.headers["ETag"] = result.etag
            resp.headers["Cache-Control"] = result.cache_control
            return resp

        # Use pre-fetched size from FilePath.size if available (P0: stat reduction)
        size = result.size
        if size is None:
            try:
                size = result.path.stat().st_size
            except OSError:
                return "Not found", 404

        # Serve small files (< 512KB) from memory -- avoids send_file overhead
        if size < 512 * 1024:
            try:
                data = result.path.read_bytes()
            except OSError:
                return "Not found", 404
            resp = await make_response(data)
            resp.headers["Content-Type"] = result.mime_type
            resp.headers["Content-Length"] = len(data)
        else:
            resp = await make_response(await send_file(str(result.path), mimetype=result.mime_type))
    else:
        # FileBytes
        resp = await make_response(result.data)
        resp.headers["Content-Type"] = result.mime_type

    if result.etag:
        resp.headers["ETag"] = result.etag
    resp.headers["Cache-Control"] = result.cache_control

    # Apply extra headers (e.g. Content-Security-Policy for SVG)
    if isinstance(result, FilePath) and result.extra_headers:
        for k, v in result.extra_headers.items():
            resp.headers[k] = v

    return resp


async def _streamable_response(result: FilePath):
    """Video/audio: delegate to send_file for Range (206) support.

    Quart's send_file uses conditional=True by default, which handles
    Accept-Ranges / Content-Range / 206 Partial Content automatically.
    Not wrapping with make_response preserves this behavior.
    """
    try:
        if not result.path.exists():
            return "Not found", 404
    except OSError:
        return "Not found", 404
    resp = await send_file(
        str(result.path),
        mimetype=result.mime_type,
        conditional=True,
    )
    if result.etag:
        resp.headers["ETag"] = result.etag
    resp.headers["Cache-Control"] = result.cache_control
    return resp
