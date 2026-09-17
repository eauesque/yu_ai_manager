"""Fernet key rotation for the secret store.

Generates a new key, re-encrypts all secret fields in config.json,
then registers the new key as active in the key ring.

Rollback guarantee:
  - All re-encrypted values are staged in memory before any disk write.
  - If save_config_json() fails the original encrypted values are restored.
  - The old key is kept in the ring for 30 days so existing enc:v2: values
    that reference the old key_id remain decryptable.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def rotate_secrets() -> dict:
    """Rotate the active Fernet key and re-encrypt all secret fields.

    Returns:
        {"ok": True, "rotated": N, "new_key_id": "k_..."}
        or {"ok": False, "error": "<message>"}
    """
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        return {"ok": False, "error": "cryptography パッケージが未インストールです"}

    from core.configuration.json_rw import load_config_json, save_config_json

    from .key_provider_keyring import (
        _active_ring_key_id,
        _key_ring,
        _load_key_ring,
        _save_key_ring,
        generate_key_id,
    )
    from .secret_store import decrypt, is_encrypted
    from .settings_schema import SETTINGS_SCHEMA, resolve_dotted_key, set_dotted_key

    # Ensure key ring is loaded before we start modifying it
    _load_key_ring()

    # Generate new key
    new_key = Fernet.generate_key()
    new_key_bytes = new_key  # generate_key() returns bytes (urlsafe_b64)
    new_key_id = generate_key_id()
    new_fernet = Fernet(new_key_bytes)

    # Load current config
    config = load_config_json()

    # Stage: decrypt + re-encrypt each secret field
    staged: list[tuple[str, str, str]] = []  # [(key_path, old_value, new_value)]
    errors: list[str] = []
    for s in SETTINGS_SCHEMA:
        if not s.secret:
            continue
        raw = resolve_dotted_key(config, s.key)
        if not isinstance(raw, str) or not raw:
            continue
        plaintext = decrypt(raw)
        if plaintext == "" and is_encrypted(raw):
            errors.append(f"復号失敗 (key={s.key}): スキップ")
            continue
        if not plaintext:
            continue
        new_enc = (
            f"enc:v2:{new_key_id}:"
            + new_fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")
        )
        staged.append((s.key, raw, new_enc))

    if errors:
        logger.warning("鍵ローテーション: 一部フィールドの復号失敗 — %s", errors)

    # Apply staged values to config dict
    old_values: dict[str, str] = {}
    for key_path, old_val, new_val in staged:
        old_values[key_path] = old_val
        set_dotted_key(config, key_path, new_val)

    # Try to save config (rollback on failure)
    try:
        save_config_json(config)
    except Exception as exc:
        # Rollback in memory
        for key_path, _old_val, _ in staged:
            set_dotted_key(config, key_path, old_values[key_path])
        logger.error("鍵ローテーション: config.json 保存失敗 — ロールバック: %s", exc)
        return {"ok": False, "error": f"config.json 保存失敗: {exc}"}

    # Register new key as active in ring
    _key_ring[new_key_id] = new_key_bytes
    old_active = _active_ring_key_id

    # Update module-level active key id (we imported the dict directly)
    import core.settings_core.key_provider as _kp
    _kp._active_ring_key_id = new_key_id

    try:
        _save_key_ring()
    except Exception as exc:
        logger.warning("鍵リング保存失敗 (インメモリのみ有効): %s", exc)

    logger.info(
        "鍵ローテーション完了: %d 件を再暗号化 (old=%s → new=%s)",
        len(staged), old_active, new_key_id,
    )
    return {"ok": True, "rotated": len(staged), "new_key_id": new_key_id}
