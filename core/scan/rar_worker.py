"""RAR scan worker compatibility shim.

External compatibility only. Repo-internal code should prefer
``rar_worker_single`` and ``rar_worker_batch`` directly.
"""

# Re-export single-entry operations
# Re-export batch operations
from core.scan.rar_worker_batch import (  # noqa: F401
    _try_cached_info_rar,
    scan_batch_rar,
)
from core.scan.rar_worker_single import (  # noqa: F401
    ScanResult,
    _backfill_rar_hash,
    _get_rar_info,
    scan_one_rar,
)
