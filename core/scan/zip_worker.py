"""ZIP scan worker compatibility shim.

External compatibility only. Repo-internal code should prefer
``zip_worker_single`` and ``zip_worker_batch`` directly.
"""

# Re-export single-entry operations
# Re-export batch operations
from core.scan.zip_worker_batch import (  # noqa: F401
    _try_cached_info,
    scan_batch_zip,
)
from core.scan.zip_worker_single import (  # noqa: F401
    ScanResult,
    _backfill_zip_hash,
    _get_zip_info,
    scan_one_zip,
)
