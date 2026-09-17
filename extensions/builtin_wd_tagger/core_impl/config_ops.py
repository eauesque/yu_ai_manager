"""Configuration operations for WD-Tagger.

Read/write wd_tagger config section in config.json.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from core.configuration.json_rw import load_config_json, save_config_json

logger = logging.getLogger(__name__)

_MIGRATION_ATTEMPTS_LIMIT = 3

# Default WD-Tagger configuration
DEFAULT_WD_TAGGER_CONFIG: dict[str, Any] = {
    "model": "SmilingWolf/wd-swinv2-tagger-v3",
    "general_threshold": 0.35,
    "character_threshold": 0.85,
    "write_xmp": True,
    "auto_download": True,
    "engine_type": "onnx",  # "onnx" | "vlm" | "both"
    "vlm_url": "http://localhost:11434",
    "vlm_model": "",
    "vlm_timeout": 60,
    "nsfw_filter": False,
}

_VALID_ENGINE_TYPES = {"onnx", "vlm", "both"}


def get_config() -> dict[str, Any]:
    """Get current WD-Tagger configuration.

    Returns a merged dict of defaults + user overrides from config.json.
    """
    config = load_config_json(None)
    user_conf = config.get("wd_tagger", {})
    merged = dict(DEFAULT_WD_TAGGER_CONFIG)
    merged.update(user_conf)
    return merged


def migrate_v1_to_v2(config_path: str = "config.json") -> dict[str, Any]:
    """Migrate wd_tagger config from v1 to v2 schema (spec § 8.2).

    v2 changes:
      - ``model`` -> ``active_model`` + ``inference_default_model``
      - new keys: ``tag_filter_mode = "union"``, ``engine_cache_size = 1``
      - idempotency marker: ``_migrated_v2 = True``

    Behaviour:
      - If ``_migrated_v2`` is already True, no-op.
      - If ``_migration_attempts`` >= 3, abort with manual-intervention
        signal (caller should surface a UI banner).
      - Otherwise: backup current config to ``config.json.bak.<ts>``,
        write new keys, mark migrated, clear ``_migration_attempts``.
      - On failure mid-migration: increment ``_migration_attempts`` and
        re-raise so the next boot can retry (or hit the abort limit).

    Returns a dict with keys:
      - ``migrated`` (bool): whether anything was changed
      - ``already_migrated`` (bool, optional): set when no-op due to marker
      - ``aborted`` (bool, optional): set when attempts limit reached
      - ``reason`` (str, optional): human reason for aborted state
      - ``backup_path`` (str, optional): path of backup file when created
    """
    config = load_config_json(None)
    wd = dict(config.get("wd_tagger") or {})

    if wd.get("_migrated_v2") is True:
        return {"migrated": False, "already_migrated": True}

    attempts = int(wd.get("_migration_attempts") or 0)
    if attempts >= _MIGRATION_ATTEMPTS_LIMIT:
        logger.error(
            "wd_tagger config migration aborted after %d attempts; "
            "manual intervention required",
            attempts,
        )
        return {
            "migrated": False,
            "aborted": True,
            "reason": (
                f"Migration attempts reached limit ({attempts} >= "
                f"{_MIGRATION_ATTEMPTS_LIMIT}). Manual intervention required: "
                "check logs and remove _migration_attempts from config.json"
            ),
        }

    # Backup the original config first — recovery target if the
    # migration write fails partway through.
    backup_path = _create_backup(config_path, original=config)

    try:
        new_wd = _build_v2_wd_section(wd)
        config_new = dict(config)
        config_new["wd_tagger"] = new_wd
        save_config_json(config_new, config_path)
    except Exception:
        # Migration write failed. Persist the incremented attempts
        # counter so the next boot can see it and eventually abort.
        # If even this fallback write fails, log but re-raise the
        # original error.
        try:
            wd_fail = dict(wd)
            wd_fail["_migration_attempts"] = attempts + 1
            config_fail = dict(config)
            config_fail["wd_tagger"] = wd_fail
            save_config_json(config_fail, config_path)
        except Exception:
            logger.exception(
                "wd_tagger config migration: failed to persist "
                "_migration_attempts counter"
            )
        logger.exception(
            "wd_tagger config migration failed; backup at %s, attempts=%d",
            backup_path, attempts + 1,
        )
        raise

    return {
        "migrated": True,
        "backup_path": str(backup_path),
    }


def _build_v2_wd_section(old_wd: dict[str, Any]) -> dict[str, Any]:
    """Compute the v2 wd_tagger section from v1 input. Pure function."""
    new_wd = dict(old_wd)
    legacy_model = old_wd.get("model") or DEFAULT_WD_TAGGER_CONFIG["model"]
    new_wd.setdefault("active_model", legacy_model)
    new_wd.setdefault("inference_default_model", legacy_model)
    new_wd.setdefault("tag_filter_mode", "union")
    new_wd.setdefault("engine_cache_size", 1)
    new_wd["_migrated_v2"] = True
    new_wd.pop("_migration_attempts", None)
    return new_wd


def _create_backup(config_path: str, original: dict) -> Path:
    """Write a timestamped backup of the original config dict."""
    import json
    ts = time.strftime("%Y%m%d-%H%M%S")
    base = Path(config_path).resolve()
    backup = base.with_name(f"{base.name}.bak.{ts}")
    backup.write_text(
        json.dumps(original, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    # Mirror json_rw.save_config_json permission tightening (best-effort).
    import contextlib
    import os
    if os.name != "nt":
        with contextlib.suppress(OSError):
            os.chmod(backup, 0o600)
    return backup


def save_config(data: dict[str, Any]) -> dict[str, Any]:
    """Save WD-Tagger configuration to config.json.

    Only saves recognized keys. Returns the saved configuration.
    """
    allowed_keys = set(DEFAULT_WD_TAGGER_CONFIG.keys())
    filtered = {k: v for k, v in data.items() if k in allowed_keys}

    # Validate thresholds
    for key in ("general_threshold", "character_threshold"):
        if key in filtered:
            val = filtered[key]
            if not isinstance(val, (int, float)) or val < 0.0 or val > 1.0:
                raise ValueError(f"{key} must be a number between 0.0 and 1.0")
            filtered[key] = round(float(val), 2)

    # Validate model
    if "model" in filtered and not isinstance(filtered["model"], str):
        raise ValueError("model must be a string")

    # Validate booleans
    for key in ("write_xmp", "auto_download", "nsfw_filter"):
        if key in filtered and not isinstance(filtered[key], bool):
            raise ValueError(f"{key} must be a boolean")

    # Validate engine_type
    if "engine_type" in filtered and filtered["engine_type"] not in _VALID_ENGINE_TYPES:
        raise ValueError(
            f"engine_type must be one of: {', '.join(sorted(_VALID_ENGINE_TYPES))}"
        )

    # Validate VLM settings
    if "vlm_url" in filtered:
        if not isinstance(filtered["vlm_url"], str):
            raise ValueError("vlm_url must be a string")
        from core.analysis.openai_compat_utils import validate_openai_compat_url
        url_err = validate_openai_compat_url(filtered["vlm_url"])
        if url_err:
            raise ValueError(f"vlm_url: {url_err}")

    if "vlm_model" in filtered and not isinstance(filtered["vlm_model"], str):
        raise ValueError("vlm_model must be a string")

    if "vlm_timeout" in filtered:
        val = filtered["vlm_timeout"]
        if not isinstance(val, (int, float)) or val < 10 or val > 300:
            raise ValueError("vlm_timeout must be an integer between 10 and 300")
        filtered["vlm_timeout"] = int(val)

    config = load_config_json(None)
    config["wd_tagger"] = {**config.get("wd_tagger", {}), **filtered}
    save_config_json(config)

    # Clear engine cache on config change
    from .engine_factory import clear_engine_cache

    clear_engine_cache()

    logger.info("WD-Tagger config saved: %s", filtered)
    return get_config()
