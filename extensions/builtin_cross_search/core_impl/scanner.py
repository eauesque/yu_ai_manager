"""Cross-search scan entrypoint wrapper."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.jobs_core.jobs_model import Job


def scan_text_files(
    scan_roots: list[str],
    job: Job | None = None,
) -> dict:
    """Delegate cross-search scanning to the service layer."""
    from core.services_core.cross_search_scan_service import (
        scan_text_files as _scan_text_files,
    )

    return _scan_text_files(scan_roots, job=job)
