"""Execution loop for background scan runtime.

Re-export shim for public API symbols.
Repo-internal imports should use ``runtime_execute_helpers`` and
``runtime_execute_loop`` directly.
"""

# Re-export helpers and constants
from core.scan.runtime_execute_helpers import (  # noqa: F401
    _lower_io_priority,
    should_compute_hash,
)

# Re-export main loop
from core.scan.runtime_execute_loop import (  # noqa: F401
    execute_scan_loop,
)
