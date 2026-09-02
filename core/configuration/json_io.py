"""JSON/YAML config file safe I/O compatibility facade."""

from .json_readers import safe_load_config, safe_load_json, safe_load_yaml
from .json_repair import repair_json_backslashes
from .json_rw import load_config_json, save_config_json

__all__ = [
    "load_config_json",
    "repair_json_backslashes",
    "safe_load_config",
    "safe_load_json",
    "safe_load_yaml",
    "save_config_json",
]
