"""Encryption key export/import in password-protected JSON format.

Exports/imports keys in password-encrypted JSON format
for secure backup and migration.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

EXPORT_VERSION = 1
PBKDF2_ITERATIONS = 600_000
MIN_PASSWORD_LENGTH = 8


def export_key(password: str) -> dict:
    """Export the current Fernet key as password-protected JSON.

    Returns:
        {"success": bool, "export_data": dict | None, "message": str}
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        return {
            "success": False,
            "export_data": None,
            "message": f"パスワードは{MIN_PASSWORD_LENGTH}文字以上必要です",
        }

    from .key_provider import get_key

    key, backend = get_key()

    # Derive wrapper key from password
    salt = os.urandom(16)
    wrapper_key = _derive_wrapper_key(password, salt)

    # Encrypt key with Fernet
    try:
        from cryptography.fernet import Fernet

        wrapper_fernet = Fernet(wrapper_key)
        encrypted_key = wrapper_fernet.encrypt(key).decode("ascii")
    except Exception as exc:
        logger.error("エクスポート暗号化に失敗: %s", exc)
        return {
            "success": False,
            "export_data": None,
            "message": "暗号化に失敗しました",
        }

    # Checksum
    checksum = hashlib.sha256(key).hexdigest()

    export_data = {
        "version": EXPORT_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "salt": base64.b64encode(salt).decode("ascii"),
        "iterations": PBKDF2_ITERATIONS,
        "encrypted_key": encrypted_key,
        "checksum": checksum,
    }

    return {
        "success": True,
        "export_data": export_data,
        "message": "エクスポートが完了しました",
    }


def import_key(export_data: dict, password: str) -> dict:
    """Import key from export data.

    Returns:
        {"success": bool, "message": str, "backend": str | None}
    """
    # Format validation
    err = validate_export_data(export_data)
    if err is not None:
        return {"success": False, "message": err, "backend": None}

    if len(password) < MIN_PASSWORD_LENGTH:
        return {
            "success": False,
            "message": f"パスワードは{MIN_PASSWORD_LENGTH}文字以上必要です",
            "backend": None,
        }

    # Restore salt
    try:
        salt = base64.b64decode(export_data["salt"])
    except Exception:
        return {
            "success": False,
            "message": "ソルトのデコードに失敗しました",
            "backend": None,
        }

    # Derive wrapper key
    wrapper_key = _derive_wrapper_key(password, salt)

    # Decrypt
    try:
        from cryptography.fernet import Fernet, InvalidToken

        wrapper_fernet = Fernet(wrapper_key)
        encrypted = export_data["encrypted_key"].encode("ascii")
        decrypted_key = wrapper_fernet.decrypt(encrypted)
    except (InvalidToken, Exception):
        return {
            "success": False,
            "message": "パスワードが正しくないか、データが破損しています",
            "backend": None,
        }

    # Checksum verification
    checksum = hashlib.sha256(decrypted_key).hexdigest()
    if checksum != export_data["checksum"]:
        return {
            "success": False,
            "message": "チェックサム不一致: データが改竄されている可能性があります",
            "backend": None,
        }

    # Save key (keychain preferred, file fallback)
    from . import keychain_backend
    from .key_provider import _key_file, _set_secure_permissions, invalidate_cache

    backend = None
    if keychain_backend.store_key(decrypted_key):
        backend = "keychain"
    else:
        key_path = _key_file().resolve()
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_bytes(decrypted_key)
        _set_secure_permissions(key_path)
        backend = "file"

    invalidate_cache()

    logger.info("鍵インポート完了 (backend=%s)", backend)
    return {
        "success": True,
        "message": "鍵のインポートが完了しました",
        "backend": backend,
    }


def validate_export_data(data: dict) -> str | None:
    """Validate export data format. Returns error message on failure, None on success."""
    if not isinstance(data, dict):
        return "エクスポートデータは辞書型である必要があります"

    required_fields = ("version", "salt", "iterations", "encrypted_key", "checksum")
    for field in required_fields:
        if field not in data:
            return f"必須フィールドが不足しています: {field}"

    if data.get("version") != EXPORT_VERSION:
        return f"未対応のバージョンです: {data.get('version')}"

    if not isinstance(data.get("iterations"), int) or data["iterations"] < 1:
        return "iterations が不正です"

    return None


def _derive_wrapper_key(password: str, salt: bytes) -> bytes:
    """Derive a wrapper Fernet key from password and salt."""
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
        dklen=32,
    )
    return base64.urlsafe_b64encode(derived)
