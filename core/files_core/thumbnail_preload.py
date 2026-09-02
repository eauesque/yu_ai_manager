"""Startup preloading of image processing libraries.

Loads and initializes pyvips / Pillow modules at server startup,
eliminating cold start delay on the first thumbnail request.

Generates a 1x1 dummy image, resizes it, and JPEG-encodes it
to complete internal buffer allocation and codec initialization.
"""

import io
import logging
import time

logger = logging.getLogger(__name__)


def preload_image_libs() -> None:
    """Preload pyvips and Pillow, and warm up codecs."""
    t0 = time.monotonic()

    # Pillow: Image + JPEG codec initialization
    try:
        from PIL import Image
        img = Image.new("RGB", (1, 1), (128, 128, 128))
        img.thumbnail((1, 1), Image.Resampling.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=78)
        buf.close()
    except Exception as exc:
        logger.debug("Pillow preload failed: %s", exc)

    # pyvips: libvips + JPEG codec initialization
    try:
        import pyvips
        vimg = pyvips.Image.black(1, 1)
        vimg.jpegsave_buffer(Q=78)
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("pyvips preload failed: %s", exc)

    elapsed = (time.monotonic() - t0) * 1000
    logger.info("  [THUMBNAIL] Image libs preloaded (%.0fms)", elapsed)
