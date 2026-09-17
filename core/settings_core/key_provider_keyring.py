"""Key ring state and rotation helpers."""

from __future__ import annotations

import base64
import datetime
import json
import logging
import os
import secrets as _secrets_mod
from pathlib import Path

from core.settings_core.key_provider_active import get_key
from core.settings_core.key_provider_storage import (
    BACKEND_FILE,
    BACKEND_KEYCHAIN,
    BACKEND_PASSPHRASE,
    _key_file,
    _set_secure_permissions,
)

logger = logging.getLogger(__name__)

_KEYRING_FILE = "keyring.json"
_key_ring: dict[str, bytes] = {}
_active_ring_key_id: str | None = None
_key_ring_loaded = False


def _keyring_file() -> Path:
    from core.paths import data_path
    return data_path(_KEYRING_FILE)


def generate_key_id() -> str:
    # Local calendar date, same value `date.today()` gave. Not
    # `now(UTC).date()`: under a positive offset that is yesterday.
    date = (
        datetime.datetime.now(tz=datetime.UTC)
        .astimezone()
        .strftime("%Y%m%d")
    )
    suffix = _secrets_mod.token_hex(4)
    return f"k_{date}{suffix}"


def _load_key_ring() -> None:
    global _key_ring, _active_ring_key_id, _key_ring_loaded
    if _key_ring_loaded:
        return

    try:
        ring_path = _keyring_file()
    except Exception:
        return

    if not ring_path.exists():
        _key_ring_loaded = True
        return

    try:
        data = json.loads(ring_path.read_text("utf-8"))
        loaded: dict[str, bytes] = {}
        for kid, b64key in data.get("keys", {}).items():
            try:
                loaded[kid] = base64.urlsafe_b64decode(b64key.encode("ascii"))
            except Exception:
                logger.warning("鍵リング: key_id=%s のデコード失敗 (スキップ)", kid)
        _key_ring = loaded
        _active_ring_key_id = data.get("active") or None
        logger.debug("鍵リング読み込み: %d 件 (active=%s)", len(_key_ring), _active_ring_key_id)
    except Exception as exc:
        logger.warning("鍵リングファイル読み込み失敗: %s", exc)

    _key_ring_loaded = True


def _save_key_ring() -> None:
    ring_path = _keyring_file()
    ring_path.parent.mkdir(parents=True, exist_ok=True)

    data: dict = {
        "keys": {
            kid: base64.urlsafe_b64encode(key).decode("ascii")
            for kid, key in _key_ring.items()
        },
        "active": _active_ring_key_id,
    }
    ring_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    _set_secure_permissions(ring_path)


def get_key_by_id(key_id: str) -> bytes | None:
    _load_key_ring()
    return _key_ring.get(key_id)


def get_active_key_with_id() -> tuple[bytes, str]:
    global _key_ring, _active_ring_key_id
    _load_key_ring()

    if _active_ring_key_id and _active_ring_key_id in _key_ring:
        return _key_ring[_active_ring_key_id], _active_ring_key_id

    primary_key, _ = get_key()
    kid = generate_key_id()
    _key_ring[kid] = primary_key
    _active_ring_key_id = kid
    try:
        _save_key_ring()
        logger.info("鍵リング初期化: 既存キーを key_id=%s として登録", kid)
    except Exception as exc:
        logger.warning("鍵リング保存失敗（インメモリのみ使用）: %s", exc)
    return primary_key, kid


def get_key_ring_info() -> dict:
    _load_key_ring()
    return {
        "active_key_id": _active_ring_key_id,
        "key_ids": list(_key_ring.keys()),
    }


def invalidate_key_ring_cache() -> None:
    global _key_ring, _active_ring_key_id, _key_ring_loaded
    _key_ring = {}
    _active_ring_key_id = None
    _key_ring_loaded = False


def get_status() -> dict:
    from . import keychain_backend

    _, current_backend = get_key()

    return {
        "active_backend": current_backend,
        "backends": {
            "passphrase": {
                "available": bool(os.environ.get("YU_SECRET_PASSPHRASE")),
                "active": current_backend == BACKEND_PASSPHRASE,
            },
            "keychain": {
                "available": keychain_backend.is_available(),
                "active": current_backend == BACKEND_KEYCHAIN,
                "backend_name": keychain_backend.get_backend_name(),
            },
            "file": {
                "available": _key_file().resolve().exists(),
                "active": current_backend == BACKEND_FILE,
                "path": str(_key_file().resolve()),
            },
        },
    }
