"""Unified key provider facade."""

from core.settings_core.key_provider_active import (
    BACKEND_FILE,
    BACKEND_KEYCHAIN,
    BACKEND_PASSPHRASE,
    get_key,
    invalidate_cache,
    migrate_to_keychain,
    warmup,
)
from core.settings_core.key_provider_keyring import (
    generate_key_id,
    get_active_key_with_id,
    get_key_by_id,
    get_key_ring_info,
    get_status,
    invalidate_key_ring_cache,
)

__all__ = [
    "BACKEND_FILE",
    "BACKEND_KEYCHAIN",
    "BACKEND_PASSPHRASE",
    "generate_key_id",
    "get_active_key_with_id",
    "get_key",
    "get_key_by_id",
    "get_key_ring_info",
    "get_status",
    "invalidate_cache",
    "invalidate_key_ring_cache",
    "migrate_to_keychain",
    "warmup",
]
