"""Scanner I/O utilities -- re-export facade.

Split into:
  - scanner_io_resolution: resolution extraction from metadata
  - scanner_io_files: file enumeration (iter_files)
  - scanner_io_archive: archive enumeration (iter_files_with_zips) and cache helpers
"""

# Re-export all public symbols for backward compatibility
from core.scan_core.scanner_io_archive import (  # noqa: F401
    iter_files_with_zips,
)
from core.scan_core.scanner_io_files import (  # noqa: F401
    ErrorCallback,
    iter_files,
)
from core.scan_core.scanner_io_resolution import (  # noqa: F401
    extract_resolution,
)
