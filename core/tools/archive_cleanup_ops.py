"""Archive cleanup operations -- re-export facade.

External-compatibility facade only.
Repo-internal imports should use the concrete implementation modules.

Split into:
  - archive_cleanup_scan: scanning for archive+folder pairs
  - archive_cleanup_execute: deletion execution with error handling
"""

# Re-export all public symbols for backward compatibility
from core.tools.archive_cleanup_execute import (  # noqa: F401
    execute_archive_cleanup,
)
from core.tools.archive_cleanup_scan import (  # noqa: F401
    ARCHIVE_EXTENSIONS,
    scan_archive_pairs,
)
