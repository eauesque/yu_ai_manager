"""Raw XMP packet I/O for PNG / JPEG / WebP.

Lifted from ``extensions/builtin_wd_tagger/core_impl/xmp_write.py`` and
``xmp_read.py``. These functions only deal with shipping a single XMP packet
into/out of the file's container; namespace-aware merging lives in
:mod:`core.tools.xmp.merge`.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PNG_XMP_KEY = "XML:com.adobe.xmp"
_JPEG_XMP_NS = b"http://ns.adobe.com/xap/1.0/\x00"


def read_xmp_packet(image_path: str | Path) -> str | None:
    """Return the raw XMP XML packet stored in an image file, or ``None``."""
    from PIL import Image

    try:
        with Image.open(image_path) as img:
            if img.format == "PNG" and hasattr(img, "text") and _PNG_XMP_KEY in img.text:
                return img.text[_PNG_XMP_KEY]
            if hasattr(img, "info") and "xmp" in img.info:
                raw = img.info["xmp"]
                if isinstance(raw, bytes):
                    return raw.decode("utf-8", errors="replace")
                return str(raw)
    except Exception as exc:  # noqa: BLE001 — third-party Pillow can raise many things
        logger.warning("Failed to read XMP from %s: %s", image_path, exc)
    return None


def write_xmp_packet(image_path: str | Path, xmp_xml: str) -> bool:
    """Write *xmp_xml* into *image_path*, replacing any existing XMP packet.

    Existing non-XMP metadata in the file (PNG ``parameters`` text chunk for
    SD/NAI, JPEG non-XMP APP segments, WebP container chunks) is preserved.
    """
    path = Path(image_path)
    suffix = path.suffix.lower()
    try:
        if suffix == ".png":
            return _write_png(path, xmp_xml)
        if suffix in (".jpg", ".jpeg"):
            return _write_jpeg(path, xmp_xml)
        if suffix == ".webp":
            return _write_webp(path, xmp_xml)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to write XMP to %s: %s", image_path, exc)
        return False
    logger.warning("XMP write not supported for format: %s", suffix)
    return False


def _write_png(path: Path, xmp_xml: str) -> bool:
    from PIL import Image
    from PIL.PngImagePlugin import PngInfo

    with Image.open(path) as img:
        png_info = PngInfo()
        # Preserve every existing text chunk except the XMP one we're replacing.
        # SD/NAI's `parameters` chunk lives here and must survive.
        if hasattr(img, "text"):
            for key, value in img.text.items():
                if key == _PNG_XMP_KEY:
                    continue
                png_info.add_text(key, value)
        png_info.add_text(_PNG_XMP_KEY, xmp_xml)

        with tempfile.NamedTemporaryFile(
            dir=path.parent, suffix=".png", delete=False
        ) as tmp:
            tmp_path = Path(tmp.name)
        try:
            img.save(tmp_path, format="PNG", pnginfo=png_info)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise
    _atomic_replace(tmp_path, path)
    logger.debug("XMP written to PNG: %s", path.name)
    return True


def _write_jpeg(path: Path, xmp_xml: str) -> bool:
    """Write XMP into a JPEG by replacing the XMP APP1 segment.

    Pillow does not natively round-trip JPEG XMP, so we splice the segment
    by hand: strip any existing XMP APP1, then insert ours right after SOI.
    """
    xmp_bytes = xmp_xml.encode("utf-8")
    app1_data = _JPEG_XMP_NS + xmp_bytes

    with open(path, "rb") as f:
        data = f.read()
    if data[:2] != b"\xff\xd8":
        logger.warning("Not a valid JPEG: %s", path)
        return False

    new_data = _remove_jpeg_xmp_app1(data)
    seg_len = len(app1_data) + 2  # length field includes itself
    app1 = b"\xff\xe1" + seg_len.to_bytes(2, "big") + app1_data
    output = new_data[:2] + app1 + new_data[2:]

    with tempfile.NamedTemporaryFile(
        dir=path.parent, suffix=".jpg", delete=False
    ) as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(output)
    _atomic_replace(tmp_path, path)
    logger.debug("XMP written to JPEG: %s", path.name)
    return True


def _remove_jpeg_xmp_app1(data: bytes) -> bytes:
    pos = 2  # skip SOI
    while pos < len(data) - 1:
        if data[pos] != 0xFF:
            break
        marker = data[pos + 1]
        if marker == 0xDA:  # SOS — image data starts, no more segments
            break
        if marker in (0x00, 0xFF):
            pos += 1
            continue
        if pos + 3 >= len(data):
            break
        seg_len = int.from_bytes(data[pos + 2 : pos + 4], "big")
        seg_end = pos + 2 + seg_len
        if marker == 0xE1 and data[pos + 4 : pos + 4 + len(_JPEG_XMP_NS)] == _JPEG_XMP_NS:
            return data[:pos] + data[seg_end:]
        pos = seg_end
    return data


def _write_webp(path: Path, xmp_xml: str) -> bool:
    from PIL import Image

    xmp_bytes = xmp_xml.encode("utf-8")
    with Image.open(path) as img:
        # quality=95: Pillow's WebP encoder defaults to 80 (lossy), which would
        # re-compress every time we just append XMP. Generation tools (NAI/SD/
        # Comfy) hand us already-encoded WebP and we have no way to recover the
        # original quality, so cap re-encode loss with 95. lossless flag is
        # similarly unrecoverable so we accept the trade-off.
        save_kwargs: dict[str, Any] = {"xmp": xmp_bytes, "quality": 95}
        exif = img.info.get("exif") if hasattr(img, "info") else None
        if exif:
            save_kwargs["exif"] = exif
        icc_profile = img.info.get("icc_profile") if hasattr(img, "info") else None
        if icc_profile:
            save_kwargs["icc_profile"] = icc_profile
        with tempfile.NamedTemporaryFile(
            dir=path.parent, suffix=".webp", delete=False
        ) as tmp:
            tmp_path = Path(tmp.name)
        try:
            img.save(tmp_path, format="WEBP", **save_kwargs)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise
    _atomic_replace(tmp_path, path)
    logger.debug("XMP written to WebP: %s", path.name)
    return True


def _atomic_replace(src: Path, dst: Path) -> None:
    try:
        shutil.move(str(src), str(dst))
    except Exception:
        src.unlink(missing_ok=True)
        raise
