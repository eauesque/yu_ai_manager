"""Storage and backend helpers for the unified key provider."""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import stat
from pathlib import Path

logger = logging.getLogger(__name__)

PBKDF2_ITERATIONS = 600_000
PBKDF2_KEY_LENGTH = 32

BACKEND_PASSPHRASE = "passphrase"
BACKEND_KEYCHAIN = "keychain"
BACKEND_FILE = "file"


def _key_file() -> Path:
    from core.paths import data_path
    return data_path("secret.key")


def _salt_file() -> Path:
    from core.paths import data_path
    return data_path("secret.salt")


def _set_secure_permissions(path: Path) -> None:
    with contextlib.suppress(OSError):
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def _get_or_create_salt() -> bytes:
    salt_path = _salt_file().resolve()
    salt_path.parent.mkdir(parents=True, exist_ok=True)

    if salt_path.exists():
        return salt_path.read_bytes()

    salt = os.urandom(16)
    salt_path.write_bytes(salt)
    _set_secure_permissions(salt_path)
    logger.info("PBKDF2 ソルトファイルを生成: %s", salt_path)
    return salt


def try_passphrase() -> bytes | None:
    passphrase = os.environ.get("YU_SECRET_PASSPHRASE")
    if not passphrase:
        return None

    salt = _get_or_create_salt()
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        passphrase.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
        dklen=PBKDF2_KEY_LENGTH,
    )
    import base64

    fernet_key = base64.urlsafe_b64encode(derived)
    logger.info("パスフレーズから暗号化鍵を導出")
    return fernet_key


def try_keychain() -> bytes | None:
    from . import keychain_backend

    key = keychain_backend.load_key()
    if key is not None:
        logger.debug("キーチェーンから暗号化鍵を取得")
    return key


def try_file() -> bytes | None:
    key_path = _key_file().resolve()
    if not key_path.exists():
        return None
    try:
        key = key_path.read_bytes().strip()
        if key:
            logger.debug("ファイルから暗号化鍵を取得: %s", key_path)
            return key
    except OSError:
        logger.warning("鍵ファイル読み込み失敗: %s", key_path)
    return None


def generate_and_store_key() -> tuple[bytes, str]:
    from cryptography.fernet import Fernet

    from . import keychain_backend

    key = Fernet.generate_key()

    if keychain_backend.store_key(key):
        logger.info("新しい暗号化鍵をキーチェーンに保存")
        return key, BACKEND_KEYCHAIN

    key_path = _key_file().resolve()
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(key)
    _set_secure_permissions(key_path)
    logger.info("新しい暗号化鍵をファイルに保存: %s", key_path)
    return key, BACKEND_FILE
