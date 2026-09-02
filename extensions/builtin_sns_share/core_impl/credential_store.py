"""Read/write SNS settings (sns section of config.json)."""

import logging
from typing import Any

from core.configuration.api import load_config_json, save_config_json
from core.settings_core.secret_store import decrypt, encrypt, is_encrypted, mask_secret

logger = logging.getLogger(__name__)

_DEFAULT_TEMPLATE = "{positive_short}\n\nModel: {model}\n#AIart"

_DEFAULT_SNS: dict[str, Any] = {
    "bluesky": {
        "handle": "",
        "app_password": "",
    },
    "post_template": _DEFAULT_TEMPLATE,
}


def load_sns_config() -> dict[str, Any]:
    """Read the sns section from config.json. Encrypted passwords are decrypted."""
    cfg = load_config_json()
    sns = cfg.get("sns", {})
    # Fill in default values
    result = dict(_DEFAULT_SNS)
    if isinstance(sns, dict):
        if "bluesky" in sns and isinstance(sns["bluesky"], dict):
            result["bluesky"] = {**_DEFAULT_SNS["bluesky"], **sns["bluesky"]}
        if "post_template" in sns:
            result["post_template"] = sns["post_template"]
    # Decrypt app_password
    bsky = result.get("bluesky", {})
    pw = bsky.get("app_password", "")
    if pw and is_encrypted(pw):
        bsky["app_password"] = decrypt(pw)
    return result


def save_sns_config(sns_data: dict[str, Any]) -> None:
    """Update the sns section of config.json. app_password is encrypted."""
    bsky = sns_data.get("bluesky", {})
    pw = bsky.get("app_password", "")
    if pw and not is_encrypted(pw):
        bsky["app_password"] = encrypt(pw)
    cfg = load_config_json()
    cfg["sns"] = sns_data
    save_config_json(cfg)
    logger.info("SNS config saved")


def get_masked_config() -> dict[str, Any]:
    """Return settings with passwords masked for the Settings UI."""
    sns = load_sns_config()
    bsky = sns.get("bluesky", {})
    pw = bsky.get("app_password", "")
    if pw:
        bsky["app_password"] = mask_secret(pw)
    return sns
