"""Safe JSON/YAML config readers."""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from .json_repair import repair_json_backslashes


def safe_load_json(path, default=None, repair_backslashes: bool = True) -> Any:
    p = Path(path)
    if not p.exists():
        return default if default is not None else {}

    try:
        raw = p.read_text(encoding="utf-8")
        return json.loads(raw)
    except json.JSONDecodeError as e:
        if repair_backslashes:
            try:
                repaired = repair_json_backslashes(raw)
                data = json.loads(repaired)
                logger.warning(f"{p.name}: invalid escapes auto-repaired")
                p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                return data
            except Exception as exc:
                logger.debug("JSON repair also failed for %s: %s", p.name, exc)
        logger.error(f"{p.name}: JSON parse failed: {e}")
        return default if default is not None else {}
    except Exception as e:
        logger.error(f"{p.name}: read failed: {e}")
        return default if default is not None else {}


def safe_load_yaml(path, default=None) -> Any:
    p = Path(path)
    if not p.exists():
        return default if default is not None else {}
    try:
        import yaml
    except ImportError:
        logger.warning(f"pyyaml not installed -- skipping {p.name}")
        return default if default is not None else {}
    try:
        raw = p.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
        return data if data is not None else (default if default is not None else {})
    except Exception as e:
        logger.error(f"{p.name}: YAML parse failed: {e}")
        return default if default is not None else {}


def safe_load_config(path, default=None) -> Any:
    p = Path(path)
    ext = p.suffix.lower()
    if ext in (".yml", ".yaml"):
        return safe_load_yaml(p, default)
    return safe_load_json(p, default)
