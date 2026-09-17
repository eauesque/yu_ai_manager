"""Bitwarden CLI integration: dynamic secret retrieval via bw command.

This module re-exports all public symbols from bw_cli and bw_ops
for backward compatibility. All logic has been split into:
  - bw_cli.py  : CLI utilities, status check, cache management
  - bw_ops.py  : secret read/resolve, folder listing, batch write
"""

from .bw_cli import (  # noqa: F401
    clear_cache,
    get_bw_status,
    is_available,
)
from .bw_ops import (  # noqa: F401
    list_folders,
    push_secrets_to_bw,
    read_secret,
    resolve_secret,
)

__all__ = [
    "clear_cache",
    "get_bw_status",
    "is_available",
    "list_folders",
    "push_secrets_to_bw",
    "read_secret",
    "resolve_secret",
]
