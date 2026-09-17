"""Bitwarden operations: read/resolve secrets, list folders, push secrets.

Re-export shim: all logic has been split into:
  - bw_read.py  : secret reading/resolving, folder listing
  - bw_write.py : batch secret write to vault
"""

from .bw_read import (  # noqa: F401
    list_folders,
    read_secret,
    resolve_secret,
)
from .bw_write import (  # noqa: F401
    push_secrets_to_bw,
)
