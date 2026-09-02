"""Compatibility facade for tools API operations.

External compatibility only. Repo-internal code should prefer the concrete
``duplicates_ops``, ``hash_ops``, ``normalize_ops``, and ``scan_ops`` modules.
"""

from core.tools.duplicates_ops import delete_duplicates, find_duplicates
from core.tools.hash_ops import start_hash_compute
from core.tools.normalize_ops import normalize_tags_api
from core.tools.scan_ops import run_tools_scan

__all__ = [
    "find_duplicates",
    "start_hash_compute",
    "delete_duplicates",
    "normalize_tags_api",
    "run_tools_scan",
]
