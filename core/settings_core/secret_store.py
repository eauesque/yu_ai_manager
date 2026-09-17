"""Fernet-based encrypted secret store.

Key retrieval is delegated to key_provider, which resolves keys in priority order:
  1. Passphrase (env var YU_SECRET_PASSPHRASE -> PBKDF2)
  2. OS keychain (keyring package)
  3. File (data/secret.key) -- legacy compatibility

Encrypted values use the "enc:v2:<key_id>:<token>" format (new installs) or the
legacy "enc:<token>" format (backward-compatible).  decrypt() handles both.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

ENC_PREFIX = "enc:"
ENC_V2_PREFIX = "enc:v2:"

# Lazy-initialised Fernet instance for legacy enc: format
_fernet = None
_current_backend: str | None = None


def _get_fernet():
    """Lazily create the Fernet instance using the primary key."""
    global _fernet, _current_backend
    if _fernet is not None:
        return _fernet

    try:
        from cryptography.fernet import Fernet
    except ImportError:
        logger.warning(
            "cryptography パッケージ未インストール: "
            "暗号化機能は無効 (uv pip install cryptography)"
        )
        return None

    from .key_provider import get_key

    key, backend = get_key()
    _current_backend = backend
    _fernet = Fernet(key)
    return _fernet


def get_current_backend() -> str | None:
    """Return the current key backend type. None if _get_fernet() has not been called."""
    return _current_backend


def encrypt(plaintext: str) -> str:
    """Encrypt plaintext using the active ring key (enc:v2: format).

    Falls back to enc: (v1) format if the key ring is unavailable.
    Returns plaintext as-is if cryptography is not installed.
    Returns as-is if already encrypted to prevent double encryption.
    """
    if not plaintext:
        return plaintext
    if is_encrypted(plaintext):
        return plaintext  # Prevent double encryption

    # Try enc:v2: format first (with key_id from ring)
    try:
        from cryptography.fernet import Fernet as _Fernet

        from .key_provider import get_active_key_with_id

        key, key_id = get_active_key_with_id()
        token = _Fernet(key).encrypt(plaintext.encode("utf-8")).decode("ascii")
        return f"{ENC_V2_PREFIX}{key_id}:{token}"
    except Exception:
        logger.warning("step failed", exc_info=True)

    f = _get_fernet()
    if f is None:
        return plaintext
    token = f.encrypt(plaintext.encode("utf-8"))
    return ENC_PREFIX + token.decode("ascii")


def decrypt(stored: str) -> str:
    """Decrypt an encrypted value (supports enc:v2: and legacy enc: formats).

    Returns empty string on decryption failure.
    Returns plaintext as-is (compatibility mode) for non-encrypted values.
    """
    if not stored:
        return stored
    if not is_encrypted(stored):
        return stored  # Return plaintext as-is

    try:
        from cryptography.fernet import Fernet as _Fernet
        from cryptography.fernet import InvalidToken
    except ImportError:
        logger.warning("cryptography 未インストール: 暗号化値を復号できません")
        return ""

    # enc:v2:<key_id>:<token>
    if stored.startswith(ENC_V2_PREFIX):
        rest = stored[len(ENC_V2_PREFIX):]
        sep = rest.find(":")
        if sep == -1:
            logger.error("enc:v2: フォーマット不正")
            return ""
        key_id = rest[:sep]
        token = rest[sep + 1:]
        try:
            from .key_provider import get_key_by_id

            key = get_key_by_id(key_id)
            if key is None:
                logger.warning(
                    "復号失敗: key_id=%s が鍵リングに存在しません。この秘密は失われた鍵で暗号化されており復元不可です。"
                    "該当 API キー/シークレットを再作成してください",
                    key_id,
                )
                return ""
            return _Fernet(key).decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, Exception):
            logger.error("復号失敗 (v2): key_id=%s", key_id)
            return ""

    # Legacy enc:<token>
    f = _get_fernet()
    if f is None:
        return ""
    try:
        token = stored[len(ENC_PREFIX):].encode("ascii")
        return f.decrypt(token).decode("utf-8")
    except Exception:
        logger.error("復号失敗: 鍵が変更された可能性があります")
        # Return empty string instead of the enc:-prefixed value to prevent
        # accidental exposure in API responses
        return ""


def is_encrypted(value: str) -> bool:
    """Check whether the value is encrypted (has enc: prefix)."""
    return isinstance(value, str) and value.startswith(ENC_PREFIX)


def mask_secret(plaintext: str) -> str:
    """Mask a secret value for display.

    Over 12 chars: first char + **** + last char
    Otherwise: ****
    """
    if not plaintext:
        return ""
    if len(plaintext) > 12:
        return plaintext[:1] + "****" + plaintext[-1:]
    return "****"


def migrate_plaintext_secrets() -> int:
    """Encrypt plaintext secrets in config.json.

    Scans keys with secret=True in settings_schema and encrypts
    plaintext values (without enc: prefix) in place.

    Returns:
        Number of keys encrypted
    """
    from core.configuration.json_rw import load_config_json, save_config_json

    from .settings_schema import SETTINGS_SCHEMA, resolve_dotted_key, set_dotted_key

    config = load_config_json()
    count = 0
    for s in SETTINGS_SCHEMA:
        if not s.secret:
            continue
        raw = resolve_dotted_key(config, s.key)
        if raw is None or not isinstance(raw, str) or not raw:
            continue
        if is_encrypted(raw):
            continue
        # Skip masked values (incomplete values returned by UI)
        if "****" in raw or "..." in raw:
            continue
        set_dotted_key(config, s.key, encrypt(raw))
        count += 1

    if count > 0:
        save_config_json(config)
        logger.info("平文シークレット %d 件を暗号化しました", count)
    return count
