"""ZIP read, info, and batch I/O operations.

Re-export shim: all logic has been split into:
  - zip_read_single.py : single-entry read, mtime/size, nested ZIP helpers
  - zip_read_batch.py  : batch info/read with serial + parallel support
"""

from .zip_read_batch import (  # noqa: F401
    batch_read_from_zip,
    batch_zip_info,
)
from .zip_read_single import (  # noqa: F401
    _is_nested_zip_path,
    _nested_zip_info,
    _nested_zip_read,
    _read_nested_zip,
    get_mtime_and_size_from_zip,
    get_mtime_from_zip,
    get_size_from_zip,
    read_bytes_from_zip,
)
