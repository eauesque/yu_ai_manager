"""Configuration operations for video analysis.

Read/write video_analysis config section in config.json.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_VIDEO_ANALYSIS_CONFIG: dict[str, Any] = {
    "enabled": True,
    "keyframe_count": 4,
    "strategy": "uniform",
    "scene_threshold": 0.4,
    "store_per_keyframe": False,
}

_VALID_STRATEGIES = {"uniform", "scene", "single"}


def get_video_config() -> dict[str, Any]:
    """Get current video_analysis configuration merged with defaults."""
    from core.configuration.json_rw import load_config_json

    config = load_config_json(None)
    user_conf = config.get("video_analysis", {})
    merged = dict(DEFAULT_VIDEO_ANALYSIS_CONFIG)
    merged.update(user_conf)
    return merged


def save_video_config(data: dict[str, Any]) -> dict[str, Any]:
    """Validate and save video_analysis config. Returns merged config."""
    from core.configuration.json_rw import load_config_json, save_config_json

    allowed_keys = set(DEFAULT_VIDEO_ANALYSIS_CONFIG.keys())
    filtered = {k: v for k, v in data.items() if k in allowed_keys}

    # Validate booleans
    for key in ("enabled", "store_per_keyframe"):
        if key in filtered and not isinstance(filtered[key], bool):
            raise ValueError(f"{key} must be a boolean")

    # Validate keyframe_count
    if "keyframe_count" in filtered:
        val = filtered["keyframe_count"]
        if not isinstance(val, int) or val < 1 or val > 16:
            raise ValueError("keyframe_count must be an integer between 1 and 16")

    # Validate strategy
    if "strategy" in filtered and filtered["strategy"] not in _VALID_STRATEGIES:
        raise ValueError(f"strategy must be one of: {', '.join(_VALID_STRATEGIES)}")

    # Validate scene_threshold
    if "scene_threshold" in filtered:
        val = filtered["scene_threshold"]
        if not isinstance(val, (int, float)) or val < 0.0 or val > 1.0:
            raise ValueError("scene_threshold must be a number between 0.0 and 1.0")
        filtered["scene_threshold"] = round(float(val), 2)

    config = load_config_json(None)
    config["video_analysis"] = {**config.get("video_analysis", {}), **filtered}
    save_config_json(config)

    logger.info("Video analysis config saved: %s", filtered)
    return get_video_config()
