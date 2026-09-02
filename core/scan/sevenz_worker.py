"""7z scan worker compatibility shim.

External compatibility only. Repo-internal code should prefer
``sevenz_worker_single`` and ``sevenz_worker_batch`` directly.
"""

# Re-export single-entry operations
# Re-export batch operations
from core.scan.sevenz_worker_batch import (  # noqa: F401
    _try_cached_info_7z,
    scan_batch_7z,
)
from core.scan.sevenz_worker_single import (  # noqa: F401
    ScanResult,
    _backfill_7z_hash,
    _get_7z_info,
    scan_one_7z,
)
