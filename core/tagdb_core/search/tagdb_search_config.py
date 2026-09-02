"""Configuration helpers for legacy tagdb search CLI."""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def load_or_default_config(path: str | None, default_config: dict[str, Any]) -> dict[str, Any]:
    cfg = dict(default_config)
    if path:
        p = Path(path)
        if p.exists():
            try:
                loaded = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    cfg.update(loaded)
            except Exception as exc:
                logger.debug("Failed to load tagdb config %s: %s", p, exc)
    return cfg
