"""Bluesky (AT Protocol) session management.

Returns a graceful error if the atproto package is not installed.
"""

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_client_instance: Any = None
_logged_in_handle: str | None = None


def _is_atproto_available() -> bool:
    """Return whether the atproto package is available."""
    try:
        import atproto  # noqa: F401
        return True
    except ImportError:
        return False


def get_client() -> tuple[Any | None, str | None]:
    """Return an authenticated atproto Client.

    Returns:
        (client, error_message) — 成功時は (client, None)
    """
    global _client_instance, _logged_in_handle

    if not _is_atproto_available():
        return None, "atproto パッケージがインストールされていません。`uv pip install atproto` を実行してください。"

    from .credential_store import load_sns_config
    sns = load_sns_config()
    bsky = sns.get("bluesky", {})
    handle = bsky.get("handle", "").strip()
    app_password = bsky.get("app_password", "").strip()

    if not handle or not app_password:
        return None, "Bluesky のハンドルまたは App Password が設定されていません。"

    with _lock:
        # Reuse if already logged in with the same handle
        if _client_instance is not None and _logged_in_handle == handle:
            return _client_instance, None

        try:
            from atproto import Client
            client = Client()
            client.login(handle, app_password)
            _client_instance = client
            _logged_in_handle = handle
            logger.info("Bluesky login successful: %s", handle)
            return client, None
        except Exception as exc:
            _client_instance = None
            _logged_in_handle = None
            logger.warning("Bluesky login failed: %s", exc)
            return None, f"Bluesky ログイン失敗: {exc}"


def clear_session() -> None:
    """Clear the session (call when settings change)."""
    global _client_instance, _logged_in_handle
    with _lock:
        _client_instance = None
        _logged_in_handle = None


def is_available() -> bool:
    """Return whether the atproto SDK is available."""
    return _is_atproto_available()
