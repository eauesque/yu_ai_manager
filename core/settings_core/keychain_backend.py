"""OS keychain integration (Windows Credential Manager / macOS Keychain / Linux Secret Service).

Securely stores encryption keys via the keyring package.
When keyring is not installed, all functions return None/False, falling back to the file backend.
"""

from __future__ import annotations

import base64
import logging
import threading
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

SERVICE_NAME = "yu-ai-manager"
KEY_ACCOUNT = "fernet-key"

_KEYRING_TIMEOUT = 3  # keyring operation timeout (seconds)

T = TypeVar("T")

# Cache for is_available() result (probe keyring only once after startup)
_available_cache: bool | None = None


def _run_with_timeout(fn: Callable[[], T], default: T) -> T:
    """Execute a keyring operation with timeout.

    Prevents API timeouts when keyring blocks (e.g., Secret Service daemon not running).
    """
    result: list[Any] = []
    error: list[Exception] = []

    def _worker():
        try:
            result.append(fn())
        except Exception as e:
            error.append(e)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout=_KEYRING_TIMEOUT)
    if t.is_alive():
        logger.debug("keyring 操作が %ds でタイムアウト", _KEYRING_TIMEOUT)
        return default
    if error:
        raise error[0]
    return result[0] if result else default


def is_available() -> bool:
    """Check whether the keyring package is available and has a valid backend."""
    global _available_cache
    if _available_cache is not None:
        return _available_cache

    try:
        from keyring.backends import fail as fail_backend
    except ImportError:
        _available_cache = False
        return False

    try:
        import keyring
        backend = _run_with_timeout(keyring.get_keyring, None)
    except Exception:
        _available_cache = False
        return False

    if backend is None:
        _available_cache = False
        return False

    # Exclude fail.Keyring as it is a dummy backend
    if isinstance(backend, fail_backend.Keyring):
        _available_cache = False
        return False

    _available_cache = True
    return True


def load_key() -> bytes | None:
    """Load Fernet key from keychain. Returns None if not stored or on error."""
    if not is_available():
        return None
    try:
        import keyring

        stored = _run_with_timeout(
            lambda: keyring.get_password(SERVICE_NAME, KEY_ACCOUNT), None
        )
        if stored is None:
            return None
        try:
            return base64.urlsafe_b64decode(stored.encode("ascii"))
        except Exception:
            logger.warning("キーチェーンの鍵データが破損しています (Base64 decode failed)")
            return None
    except Exception:
        logger.debug("キーチェーンからの鍵読み込みに失敗")
        return None


def store_key(key: bytes) -> bool:
    """Store Fernet key in keychain. Returns True on success."""
    if not is_available():
        return False
    try:
        import keyring

        encoded = base64.urlsafe_b64encode(key).decode("ascii")
        _run_with_timeout(
            lambda: keyring.set_password(SERVICE_NAME, KEY_ACCOUNT, encoded), None
        )
        return True
    except Exception:
        logger.warning("キーチェーンへの鍵保存に失敗")
        return False


def delete_key() -> bool:
    """Delete key from keychain. Returns True on success."""
    if not is_available():
        return False
    try:
        import keyring

        _run_with_timeout(
            lambda: keyring.delete_password(SERVICE_NAME, KEY_ACCOUNT), None
        )
        return True
    except Exception:
        logger.debug("キーチェーンからの鍵削除に失敗 (未保存の可能性)")
        return False


def get_backend_name() -> str | None:
    """Return the backend name for UI display (e.g., WinVaultKeyring, Keychain)."""
    if not is_available():
        return None
    try:
        import keyring
        backend = _run_with_timeout(keyring.get_keyring, None)
        if backend is None:
            return None
        return type(backend).__name__
    except Exception:
        return None
