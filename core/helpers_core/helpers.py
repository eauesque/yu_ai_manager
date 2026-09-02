"""Legacy helper facade.

External compatibility only. Repo-internal code should prefer the concrete
``helpers_*`` modules and ``core.platform`` helpers directly.
"""

from .helpers_runtime import VENDOR_LIBS, cleanup_thumbnail_cache, ensure_vendor_libs
from .helpers_text_path import (
    archive_part,
    is_archive_member,
    norm_space,
    normalize_path,
    resolve_real_path,
    sanitize_user_path,
    split_archive_path,
    split_namespace,
)

__all__ = [
    "archive_part",
    "is_archive_member",
    "norm_space",
    "split_archive_path",
    "split_namespace",
    "normalize_path",
    "resolve_real_path",
    "sanitize_user_path",
    "VENDOR_LIBS",
    "ensure_vendor_libs",
    "cleanup_thumbnail_cache",
]
