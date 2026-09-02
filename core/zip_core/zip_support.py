"""ZIP support compatibility facade.

External-compatibility facade only.
Repo-internal imports should use the concrete implementation modules.
"""

from .zip_support_core import (
    get_mtime_from_zip,
    get_size_from_zip,
    is_zip_path,
    list_images_in_zip,
    read_bytes_from_zip,
)
from .zip_support_extract import extract_metadata_from_zip

__all__ = [
    "extract_metadata_from_zip",
    "get_mtime_from_zip",
    "get_size_from_zip",
    "is_zip_path",
    "list_images_in_zip",
    "read_bytes_from_zip",
]
