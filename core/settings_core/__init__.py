"""Settings core: encrypted secret store + settings schema + 1Password CLI integration."""

from .secret_store import decrypt, encrypt, is_encrypted, mask_secret
from .settings_schema import (
    SETTINGS_SCHEMA,
    get_schema,
    resolve_dotted_key,
    set_dotted_key,
)

__all__ = [
    "encrypt",
    "decrypt",
    "is_encrypted",
    "mask_secret",
    "SETTINGS_SCHEMA",
    "get_schema",
    "resolve_dotted_key",
    "set_dotted_key",
]
