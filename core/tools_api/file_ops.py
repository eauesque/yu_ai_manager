"""File search/inspect helpers for tools routes."""

from core.tools.services_file_search import file_search_service
from core.tools.services_inspect_upload import inspect_uploaded_file


def file_search_payload(query: str, meta_filter: str, limit: int):
    """Run DB-backed file search payload builder."""
    return file_search_service(query, meta_filter, limit)


def inspect_uploaded_file_payload(uploaded_file, zip_entry=""):
    """Inspect uploaded media metadata."""
    return inspect_uploaded_file(uploaded_file, zip_entry=zip_entry)
