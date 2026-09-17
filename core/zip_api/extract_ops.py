"""Extract operations for ZIP file routes."""

from typing import Any


def extract_from_zip(file_id: Any, remote_addr: str):
    """Extract one ZIP member and register it in DB."""
    from core.services_core.zip_extract_service import extract_from_archive

    return extract_from_archive(file_id, remote_addr)
