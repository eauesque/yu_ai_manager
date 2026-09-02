"""Source browser -- re-export facade.

External-compatibility facade only.
Repo-internal imports should use the concrete implementation modules.

Split into:
  - source_browser_security: path validation, access control definitions
  - source_browser_ops: tree, read, search operations
"""

# Re-export all public symbols for backward compatibility
from core.source_core.source_browser_ops import (  # noqa: F401
    source_read,
    source_search,
    source_tree,
)
from core.source_core.source_browser_security import (  # noqa: F401
    ALLOWED_EXTENSIONLESS,
    ALLOWED_EXTENSIONS,
    BLOCKED_DIRS,
    BLOCKED_PATTERNS,
    MAX_FILE_SIZE_BYTES,
    MAX_LINES,
    MAX_SEARCH_RESULTS,
    MAX_TREE_DEPTH,
)
