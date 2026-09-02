"""Scan-roots config I/O helpers."""

import logging
from pathlib import Path

from core.configuration.json_rw import effective_config_path
from core.configuration.json_rw import load_config_json as _load_config
from core.configuration.json_rw import save_config_json as _save_config

logger = logging.getLogger(__name__)


def load_config_json(config_path: str | None = None) -> dict:
    return _load_config(config_path)


def save_config_json(config: dict, config_path: str | None = None) -> None:
    _save_config(config, config_path)
    logger.info("Saved config: %s", Path(effective_config_path(config_path) or config_path or "config.json").resolve())
