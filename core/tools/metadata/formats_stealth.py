"""Stealth metadata extraction helpers (Tensor.art etc.)."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_stealth(image_path: Path) -> tuple[str | None, str | None, str, str | None]:
    """Extract stealth metadata markers from raw bytes."""
    try:
        with open(image_path, "rb") as f:
            data = f.read()

        marker = b"stealth_pngcomp"
        idx = data.find(marker)
        if idx == -1:
            return (None, None, "unknown", None)

        json_start = idx + len(marker)
        json_data = data[json_start:]

        try:
            for end in range(100, min(len(json_data), 50000), 100):
                try:
                    meta = json.loads(json_data[:end].decode("utf-8", errors="ignore"))
                    positive = meta.get("prompt") or meta.get("positive_prompt")
                    negative = meta.get("negative_prompt")
                    return (positive, negative, "stealth_png_webp", json.dumps(meta, ensure_ascii=False))
                except Exception:  # noqa: S112 -- inner parse attempt; the enclosing handler already logs at debug
                    continue
        except Exception as exc:
            logger.debug("Stealth JSON parse failed: %s", exc)

        return (None, None, "stealth_png_webp", None)
    except Exception:
        return (None, None, "unknown", None)
