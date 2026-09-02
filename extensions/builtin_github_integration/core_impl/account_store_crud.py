"""GitHub account store — CRUD operations + token management."""

from __future__ import annotations

import logging
from typing import Any

from core.configuration.api import load_config_json, save_config_json
from core.settings_core.secret_store import decrypt, encrypt, is_encrypted, mask_secret

logger = logging.getLogger(__name__)


def _token_setting_key(label: str) -> str:
    """Return the settings schema key for a GitHub account token.

    Tokens are stored at github_integration.tokens.<label> (flat dict)
    instead of inside the accounts[] array, so the standard
    resolve_dotted_key / set_dotted_key functions work correctly
    with the Settings system (1Password, Bitwarden, Secrets tab).
    """
    return f"github_integration.tokens.{label}"


def _register_token_setting(label: str) -> None:
    """Register a GitHub account token in the settings schema."""
    from core.settings_core.settings_schema import SettingDef, register_dynamic_setting
    register_dynamic_setting(SettingDef(
        _token_setting_key(label), "str",
        f"GitHub PAT ({label})", "",
        secret=True, category="github", op_eligible=True,
    ))


def _unregister_token_setting(label: str) -> None:
    """Remove a GitHub account token from the settings schema."""
    from core.settings_core.settings_schema import unregister_dynamic_setting
    unregister_dynamic_setting(_token_setting_key(label))


def sync_token_settings() -> None:
    """Register all existing GitHub account tokens in the settings schema.

    Called at server startup. Also migrates tokens from the legacy
    accounts[].token location to the new github_integration.tokens.{label}.
    """
    sec = _section()
    tokens = sec.setdefault("tokens", {})
    migrated = False

    for acc in sec.get("accounts", []):
        label = acc.get("label", "")
        if not label:
            continue
        _register_token_setting(label)
        # Migrate from legacy accounts[].token to tokens dict
        old_token = acc.get("token", "")
        if old_token and label not in tokens:
            tokens[label] = old_token
            acc.pop("token", None)
            migrated = True

    if migrated:
        _save_section(sec)
        logger.info("GitHub tokens migrated to settings-managed storage")


def _section() -> dict:
    """Load github_integration section from config."""
    cfg = load_config_json()
    return cfg.get("github_integration", {})


def _save_section(section: dict) -> None:
    """Save github_integration section to config."""
    cfg = load_config_json()
    cfg["github_integration"] = section
    save_config_json(cfg)


def _get_token(label: str) -> str:
    """Get decrypted token for a label from the tokens dict."""
    sec = _section()
    tokens = sec.get("tokens", {})
    raw = tokens.get(label, "")
    # Fallback: check legacy accounts[].token
    if not raw:
        for acc in sec.get("accounts", []):
            if acc.get("label") == label:
                raw = acc.get("token", "")
                break
    if is_encrypted(raw):
        return decrypt(raw)
    return raw


def list_accounts() -> list[dict[str, Any]]:
    """List all registered accounts (tokens masked)."""
    sec = _section()
    accounts = sec.get("accounts", [])
    result = []
    for acc in accounts:
        label = acc.get("label", "")
        token_raw = _get_token(label)
        result.append({
            "label": label,
            "repos": acc.get("repos", []),
            "enabled": acc.get("enabled", True),
            "token_masked": mask_secret(token_raw) if token_raw else "",
            "token_setting_key": _token_setting_key(label),
        })
    return result


def get_account(label: str) -> dict | None:
    """Get a single account by label (with decrypted token)."""
    sec = _section()
    for acc in sec.get("accounts", []):
        if acc.get("label") == label:
            return {
                "label": acc["label"],
                "token": _get_token(label),
                "repos": acc.get("repos", []),
                "enabled": acc.get("enabled", True),
            }
    return None


def add_account(
    label: str, token: str, repos: list[str] | None = None
) -> dict:
    """Add a new GitHub account. Token is encrypted before storage."""
    sec = _section()
    accounts = sec.setdefault("accounts", [])

    # Check duplicate label
    for acc in accounts:
        if acc.get("label") == label:
            raise ValueError(f"Account '{label}' already exists")

    entry = {
        "label": label,
        "repos": repos or [],
        "enabled": True,
    }
    accounts.append(entry)
    # Store token in the flat tokens dict (Settings-managed)
    tokens = sec.setdefault("tokens", {})
    tokens[label] = encrypt(token) if token else ""
    _save_section(sec)
    _register_token_setting(label)
    logger.info("GitHub account added: %s", label)
    return {"label": label, "repos": repos or [], "enabled": True}


def remove_account(label: str) -> bool:
    """Remove an account by label."""
    sec = _section()
    accounts = sec.get("accounts", [])
    before = len(accounts)
    sec["accounts"] = [a for a in accounts if a.get("label") != label]
    if len(sec["accounts"]) == before:
        return False
    # Remove token from tokens dict
    tokens = sec.get("tokens", {})
    tokens.pop(label, None)
    _save_section(sec)
    _unregister_token_setting(label)
    logger.info("GitHub account removed: %s", label)
    return True


def update_account(
    label: str,
    token: str | None = None,
    repos: list[str] | None = None,
    enabled: bool | None = None,
) -> dict | None:
    """Update an existing account."""
    sec = _section()
    for acc in sec.get("accounts", []):
        if acc.get("label") != label:
            continue
        if token is not None:
            tokens = sec.setdefault("tokens", {})
            tokens[label] = encrypt(token) if token else ""
        if repos is not None:
            acc["repos"] = repos
        if enabled is not None:
            acc["enabled"] = enabled
        _save_section(sec)
        return {"label": label, "repos": acc["repos"], "enabled": acc["enabled"]}
    return None
