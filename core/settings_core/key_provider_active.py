"""Active key selection and migration helpers."""

from __future__ import annotations

import logging

from core.settings_core.key_provider_storage import (
    BACKEND_FILE,
    BACKEND_KEYCHAIN,
    BACKEND_PASSPHRASE,
    _key_file,
    generate_and_store_key,
    try_file,
    try_keychain,
    try_passphrase,
)

logger = logging.getLogger(__name__)

_cached_key: bytes | None = None
_cached_backend: str | None = None
_warmup_done = False


def get_key() -> tuple[bytes, str]:
    global _cached_key, _cached_backend
    if _cached_key is not None:
        return _cached_key, _cached_backend  # type: ignore[return-value]

    key = try_passphrase()
    if key is not None:
        _cached_key, _cached_backend = key, BACKEND_PASSPHRASE
        return key, BACKEND_PASSPHRASE

    key = try_keychain()
    if key is not None:
        _cached_key, _cached_backend = key, BACKEND_KEYCHAIN
        return key, BACKEND_KEYCHAIN

    key = try_file()
    if key is not None:
        _cached_key, _cached_backend = key, BACKEND_FILE
        return key, BACKEND_FILE

    key, backend = generate_and_store_key()
    _cached_key, _cached_backend = key, backend
    return key, backend


def invalidate_cache() -> None:
    global _cached_key, _cached_backend, _warmup_done
    _cached_key = None
    _cached_backend = None
    _warmup_done = False


def warmup() -> None:
    global _warmup_done
    if _warmup_done:
        return
    _warmup_done = True

    import threading

    def _do() -> None:
        try:
            get_key()
            logger.debug("鍵プリロード完了 (backend=%s)", _cached_backend)
        except Exception:
            logger.debug("鍵プリロード失敗", exc_info=True)

    threading.Thread(target=_do, daemon=True, name="key-warmup").start()


def migrate_to_keychain() -> dict:
    from . import keychain_backend

    if not keychain_backend.is_available():
        return {
            "success": False,
            "message": "keyring パッケージが利用できません",
            "backend": _cached_backend or "unknown",
        }

    key, current = get_key()

    if current == BACKEND_KEYCHAIN:
        return {
            "success": True,
            "message": "既にキーチェーンバックエンドを使用中です",
            "backend": BACKEND_KEYCHAIN,
        }

    if not keychain_backend.store_key(key):
        return {
            "success": False,
            "message": "キーチェーンへの保存に失敗しました",
            "backend": current,
        }

    key_path = _key_file().resolve()
    if key_path.exists():
        try:
            key_path.unlink()
            logger.info("鍵ファイルを削除: %s", key_path)
        except OSError:
            logger.warning("鍵ファイルの削除に失敗: %s", key_path)

    invalidate_cache()
    return {
        "success": True,
        "message": "キーチェーンへの移行が完了しました",
        "backend": BACKEND_KEYCHAIN,
    }
