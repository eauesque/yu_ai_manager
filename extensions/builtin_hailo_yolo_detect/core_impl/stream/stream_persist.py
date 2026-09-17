"""JSON persistence for stream sources and detection rules.

Saves to ``<extension_dir>/data/stream_config.json``.
Thread-safe: uses a lock around file writes.

The file is owned and encrypted by the Rust implementation
(``crates/yu-server/src/routes/hailo_yolo_stream/``); these routes are no longer
registered in production. Reading is kept working — and only reading — so that
reverting the T9 cutover finds a config it can still parse. This side never
encrypts, so a rollback leaves the file in the clear until Rust owns it again.
See ``docs/superpowers/specs/2026-08-14-stream-config-secret-store-design.md``.
This file is also the second-implementation oracle for the on-disk schema;
the Python reader smoke in ``crates/yu-server/src/routes/hailo_yolo_stream/config.rs`` uses it.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).resolve().parents[2] / "data"
_CONFIG_FILE = _CONFIG_DIR / "stream_config.json"
_write_lock = threading.Lock()

# Must stay identical to SECRET_KEYS / URL_KEYS in the Rust `secrets` module.
_SECRET_KEYS = frozenset({
    "secret", "token", "api_key", "apikey", "password", "passwd",
    "authorization", "auth", "access_token", "refresh_token",
})
_URL_KEYS = frozenset({"url", "endpoint", "webhook_url", "callback_url"})


class _DecryptFailed(Exception):
    """An encrypted value could not be recovered."""


def _decrypt_value(value: str) -> str:
    from core.settings_core.secret_store import decrypt, is_encrypted

    if not value or not is_encrypted(value):
        return value
    plain = decrypt(value)
    # encrypt() never encrypts an empty string, so ciphertext in and empty out
    # can only mean the decryption failed. Returning "" here would leave a
    # webhook with no secret, and an absent secret means an unsigned request.
    if not plain:
        raise _DecryptFailed
    return plain


def _decrypt_tree(node: Any) -> Any:
    if isinstance(node, dict):
        return {
            key: _decrypt_value(value)
            if isinstance(value, str) and key.lower() in (_SECRET_KEYS | _URL_KEYS)
            else _decrypt_tree(value)
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [_decrypt_tree(item) for item in node]
    return node


def _decrypt_entries(entries: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    """Decrypt protected values, refusing everything if any value is unreadable.

    Dropping only the unreadable entries would delete secrets for good when a key
    is merely unavailable. Refusing wholesale keeps the file intact and is still
    fail-closed: nothing loaded is nothing fired.
    """
    if not isinstance(entries, list):
        # Hand a malformed shape back untouched. Coercing it to a list here would
        # turn "the file is wrong" into a silent empty result.
        return entries
    try:
        return [_decrypt_tree(entry) for entry in entries]
    except _DecryptFailed:
        logger.error(
            "Refusing to load stream %s: an encrypted value could not be decrypted. "
            "Restore the secret key, or remove the unreadable entries by hand.",
            kind,
        )
        return []


def _read_config_unlocked() -> dict[str, Any]:
    """Load config from disk. Returns empty dict on missing/corrupt file.
    Caller must hold _write_lock.
    """
    if not _CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read stream config: %s", exc)
        return {}


def _write_config_unlocked(data: dict[str, Any]) -> None:
    """Write config to disk atomically. Caller must hold _write_lock."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _CONFIG_FILE.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(_CONFIG_FILE)


# -- Public API --------------------------------------------------------

def save_sources(sources: list[dict[str, Any]]) -> None:
    """Persist source definitions (id, url, name only)."""
    with _write_lock:
        cfg = _read_config_unlocked()
        cfg["sources"] = sources
        _write_config_unlocked(cfg)
    logger.debug("Saved %d sources to %s", len(sources), _CONFIG_FILE)


def load_sources() -> list[dict[str, Any]]:
    """Load persisted source definitions."""
    with _write_lock:
        sources = _read_config_unlocked().get("sources", [])
    return _decrypt_entries(sources, "sources")


def save_rules(rules: list[dict[str, Any]]) -> None:
    """Persist detection rules."""
    with _write_lock:
        cfg = _read_config_unlocked()
        cfg["rules"] = rules
        _write_config_unlocked(cfg)
    logger.debug("Saved %d rules to %s", len(rules), _CONFIG_FILE)


def load_rules() -> list[dict[str, Any]]:
    """Load persisted detection rules."""
    with _write_lock:
        rules = _read_config_unlocked().get("rules", [])
    return _decrypt_entries(rules, "rules")
