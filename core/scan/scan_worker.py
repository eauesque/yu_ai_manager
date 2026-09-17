"""Scan worker process — re-export shim for backward compatibility.

Usage:
    python -m core.scan.scan_worker start --db PATH --root PATH [options]
    python -m core.scan.scan_worker scan-all --db PATH [--force] [options]
    python -m core.scan.scan_worker stop
    python -m core.scan.scan_worker status
"""

import sys
from pathlib import Path

# Add project root to sys.path
_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Re-export job class and helpers
# Re-export CLI commands
from core.scan.scan_worker_cli import (  # noqa: F401
    cmd_scan_all,
    cmd_start,
    cmd_status,
    cmd_stop,
    main,
)
from core.scan.scan_worker_job import (  # noqa: F401
    FileBasedJob,
)

if __name__ == "__main__":
    main()
