"""Image placeholder rendering and cached image responses."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .response_types import FilePath, FileResult

if TYPE_CHECKING:
    from .thumbnail_common import CacheStat

_THUMBNAIL_CACHE_CONTROL = "public, max-age=86400, immutable, stale-while-revalidate=604800"


def _mime_for_cached(cache_path: Path) -> str:
    """Guess MIME type from the cache file extension."""
    suffix = cache_path.suffix.lower()
    if suffix == ".webp":
        return "image/webp"
    return "image/jpeg"


def send_cached_image(cache_path: Path, mimetype: str | None = None, *, cs: CacheStat | None = None) -> FileResult:
    """Build a FilePath response for a cached thumbnail.

    When *cs* (CacheStat) is provided the extra stat() syscall is skipped.
    """
    if cs is None:
        from .thumbnail_common import CacheStat
        cs = CacheStat.from_path(cache_path)
    if cs is None:
        # File disappeared between check and serve
        st = cache_path.stat()
        etag = f'"{st.st_size:x}-{int(st.st_mtime):x}"'
        size = st.st_size
    else:
        etag = cs.etag
        size = cs.size
    return FilePath(
        path=cache_path,
        mime_type=mimetype or _mime_for_cached(cache_path),
        etag=etag,
        cache_control=_THUMBNAIL_CACHE_CONTROL,
        size=size,
    )


def heif_placeholder(cache_path: Path) -> FileResult:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (400, 300), (30, 30, 50))
    draw = ImageDraw.Draw(img)
    draw.text((200, 120), "HEIF/HEIC", fill=(150, 150, 200), anchor="mm")
    draw.text((200, 160), "pip install pillow-heif", fill=(100, 100, 140), anchor="mm")
    draw.text((200, 190), "to enable thumbnails", fill=(100, 100, 140), anchor="mm")
    img.save(cache_path, "JPEG", quality=85)
    return send_cached_image(cache_path)


def jxl_placeholder(cache_path: Path) -> FileResult:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (400, 300), (35, 28, 28))
    draw = ImageDraw.Draw(img)
    draw.text((200, 120), "JPEG XL (.jxl)", fill=(230, 180, 150), anchor="mm")
    draw.text((200, 160), "Pillow/libjxl not available", fill=(170, 120, 120), anchor="mm")
    draw.text((200, 190), "Install JPEG XL support", fill=(170, 120, 120), anchor="mm")
    img.save(cache_path, "JPEG", quality=85)
    return send_cached_image(cache_path)


def svg_placeholder(cache_path: Path) -> FileResult:
    """Fallback placeholder when resvg is not available for SVG thumbnails."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (400, 300), (28, 36, 42))
    draw = ImageDraw.Draw(img)
    draw.text((200, 108), "SVG", fill=(140, 200, 240), anchor="mm")
    draw.text((200, 150), "pip install resvg", fill=(100, 150, 180), anchor="mm")
    draw.text((200, 182), "to enable thumbnails", fill=(100, 150, 180), anchor="mm")
    img.save(cache_path, "JPEG", quality=85)
    return send_cached_image(cache_path)


def unsupported_image_placeholder(cache_path: Path, ext: str = "") -> FileResult:
    from PIL import Image, ImageDraw

    label = (ext or "UNKNOWN").upper()
    img = Image.new("RGB", (400, 300), (30, 30, 30))
    draw = ImageDraw.Draw(img)
    draw.text((200, 120), f"Unsupported image ({label})", fill=(220, 220, 220), anchor="mm")
    draw.text((200, 160), "Install decoder support", fill=(150, 150, 150), anchor="mm")
    img.save(cache_path, "JPEG", quality=85)
    return send_cached_image(cache_path)


def pdf_placeholder(cache_path: Path) -> FileResult:
    """Fallback placeholder when poppler (pdf2image) is not available."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (400, 300), (40, 30, 30))
    draw = ImageDraw.Draw(img)
    draw.text((200, 108), "PDF", fill=(220, 180, 160), anchor="mm")
    draw.text((200, 150), "install poppler", fill=(160, 130, 120), anchor="mm")
    draw.text((200, 182), "to enable thumbnails", fill=(140, 110, 100), anchor="mm")
    img.save(cache_path, "JPEG", quality=85)
    return send_cached_image(cache_path)


_TRANSIENT_PLACEHOLDER_CACHE: bytes | None = None


def _transient_error_placeholder_bytes() -> FileResult:
    """In-memory placeholder for *transient* generation errors.

    Unlike `corrupt_file_placeholder`, this does NOT write to the cache
    directory, so a one-off error (ImportError during a deploy, brief
    OSError, lock acquisition failure) cannot poison the cache and stick
    a "FILE ERROR" JPEG in front of a perfectly readable archive entry.
    """
    from .response_types import FileBytes

    global _TRANSIENT_PLACEHOLDER_CACHE
    if _TRANSIENT_PLACEHOLDER_CACHE is None:
        import io as _io

        from PIL import Image, ImageDraw

        img = Image.new("RGB", (400, 300), (40, 36, 30))
        draw = ImageDraw.Draw(img)
        draw.text((200, 130), "loading...", fill=(200, 190, 170), anchor="mm")
        draw.text((200, 168), "(retry shortly)", fill=(150, 140, 120), anchor="mm")
        buf = _io.BytesIO()
        img.save(buf, "JPEG", quality=80)
        _TRANSIENT_PLACEHOLDER_CACHE = buf.getvalue()
    return FileBytes(
        data=_TRANSIENT_PLACEHOLDER_CACHE,
        mime_type="image/jpeg",
        cache_control="no-store",
    )


def corrupt_file_placeholder(cache_path: Path, hint: str = "") -> FileResult:
    """Placeholder for corrupt/unreadable files (broken ZIP, incomplete video, etc.)."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (400, 300), (50, 30, 30))
    draw = ImageDraw.Draw(img)
    draw.text((200, 108), "FILE ERROR", fill=(220, 120, 120), anchor="mm")
    if hint:
        safe = hint.encode("latin-1", errors="replace").decode("latin-1")
        short = (safe[:40] + "...") if len(safe) > 40 else safe
        draw.text((200, 156), short, fill=(180, 130, 130), anchor="mm")
    draw.text((200, 188), "broken or incomplete file", fill=(140, 100, 100), anchor="mm")
    img.save(cache_path, "JPEG", quality=85)
    return send_cached_image(cache_path)


def audio_placeholder(cache_path: Path, name: str = "") -> FileResult:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (400, 300), (18, 24, 36))
    draw = ImageDraw.Draw(img)
    draw.text((200, 108), "AUDIO", fill=(173, 216, 255), anchor="mm")
    if name:
        # Pillow default font only supports latin-1; replace non-encodable chars
        safe = name.encode("latin-1", errors="replace").decode("latin-1")
        short = (safe[:34] + "...") if len(safe) > 35 else safe
        draw.text((200, 156), short, fill=(160, 176, 196), anchor="mm")
    draw.text((200, 188), "audio file placeholder", fill=(120, 136, 156), anchor="mm")
    img.save(cache_path, "JPEG", quality=85)
    return send_cached_image(cache_path)
