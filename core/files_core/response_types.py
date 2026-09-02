"""Framework-neutral response types for file serving.

These dataclasses allow core/ modules to return file data
without depending on Flask (or any other web framework).
The route layer converts them to framework-specific responses.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FileBytes:
    """In-memory bytes (converted images, archive entries, etc.)."""
    data: bytes
    mime_type: str
    etag: str | None = None
    cache_control: str = "public, max-age=31536000"


@dataclass(frozen=True, slots=True)
class FilePath:
    """On-disk file (sendfile optimisation possible)."""
    path: Path
    mime_type: str
    etag: str | None = None
    cache_control: str = "public, max-age=31536000"
    size: int | None = None  # pre-fetched size avoids extra stat()
    extra_headers: dict | None = None  # additional response headers (e.g. CSP for SVG)


@dataclass(frozen=True, slots=True)
class FileError:
    """Error response."""
    message: str
    status_code: int


FileResult = FileBytes | FilePath | FileError
