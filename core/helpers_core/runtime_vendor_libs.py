"""Vendor library bootstrap helpers."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

VENDOR_LIBS = [
    (
        "qrcode.min.js",
        "ui/default/static/vendor/qrcode.min.js",
        "https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js",
    ),
    (
        "jsQR.min.js",
        "ui/default/static/vendor/jsQR.min.js",
        "https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.min.js",
    ),
]


def ensure_vendor_libs(base_dir: str | None = None):
    import urllib.request

    base = Path(base_dir) if base_dir else Path(".")

    for name, rel_path, url in VENDOR_LIBS:
        local = base / rel_path
        if local.exists() and local.stat().st_size > 100:
            continue

        local.parent.mkdir(parents=True, exist_ok=True)
        try:
            urllib.request.urlretrieve(url, str(local))
            size_kb = local.stat().st_size / 1024
            logger.info(f"  [OK] Downloaded {name} ({size_kb:.1f} KB)")
        except Exception as e:
            logger.warning(f"  Could not download {name}: {e}")
            logger.warning("    CDN fallback will be used at runtime")
