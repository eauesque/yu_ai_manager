"""Raw metadata read helpers for tools API."""


def extract_raw_metadata(filepath, ext):
    """Extract raw metadata for display."""
    result = {}
    try:
        if ext == ".png":
            from PIL import Image

            with Image.open(filepath) as img:
                if img.info:
                    for k, v in img.info.items():
                        if isinstance(v, (str, int, float)):
                            result[k] = str(v)[:2000]
        elif ext in (".jpg", ".jpeg"):
            from PIL import Image

            with Image.open(filepath) as img:
                exif = img.getexif()
                if exif:
                    for k, v in exif.items():
                        result[str(k)] = str(v)[:500]
        elif ext == ".webp":
            from PIL import Image

            # WebP container fields like 'loop' / 'background' are not real metadata —
            # ignore them when deciding whether to fall back to EXIF UserComment.
            _WEBP_CONTAINER_KEYS = {"loop", "background", "duration", "exif", "icc_profile", "xmp"}
            with Image.open(filepath) as img:
                if img.info:
                    for k, v in img.info.items():
                        if isinstance(v, (str, int, float)):
                            result[k] = str(v)[:2000]
            has_real_meta = any(k not in _WEBP_CONTAINER_KEYS for k in result)
            # Also try EXIF (NovelAI WebP stores metadata in EXIF UserComment)
            if not has_real_meta:
                from pathlib import Path as _Path

                from core.extractors import extract_novelai_webp_metadata
                nai_meta = extract_novelai_webp_metadata(_Path(filepath))
                if nai_meta:
                    result["EXIF_UserComment"] = nai_meta[:4000]
    except Exception as e:
        result["_error"] = str(e)
    return result
