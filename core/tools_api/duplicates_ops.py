"""Duplicate/hash/scan helper payloads for tools routes."""

from typing import Any

from core.tools.duplicates_ops import delete_duplicates, find_duplicates
from core.tools.hash_ops import start_hash_compute
from core.tools.normalize_ops import normalize_tags_api
from core.tools.scan_ops import run_tools_scan


def find_duplicates_payload(args) -> tuple[dict[str, Any], int]:
    """Parse query args and run duplicate search."""
    cross_directory = args.get("cross_directory", "false").lower() == "true"
    method = args.get("method", "hash")
    try:
        threshold = int(args.get("threshold", "5"))
    except (TypeError, ValueError):
        return {"error": "Invalid threshold (must be an integer 0-64)"}, 400
    # 64-bit pHash hamming distance cannot exceed 64; reject out-of-range
    # to avoid silently empty results or accidental whole-DB unions.
    if threshold < 0 or threshold > 64:
        return {"error": "Invalid threshold (must be 0-64)"}, 400
    return find_duplicates(cross_directory, method, threshold)


def compute_hashes_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Parse request body and start hash compute job."""
    hash_type = data.get("type", "both")
    limit = int(data.get("limit", 5000))
    return start_hash_compute(hash_type, limit)


def delete_duplicates_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Delete duplicates based on request payload."""
    groups = data.get("groups", [])
    mode = data.get("mode", "soft")
    return delete_duplicates(groups, mode)


def normalize_tags_payload(args) -> dict[str, Any]:
    """Normalize tags payload from query args."""
    dry_run = args.get("dry_run", "false").lower() == "true"
    return normalize_tags_api(dry_run)


def tools_scan_payload(data: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Run tools scan using request body values."""
    path = data.get("path")
    recursive = data.get("recursive", True)
    scan_zips = data.get("scan_zips", False)
    compute_hash = data.get("compute_hash", False)
    return run_tools_scan(path, recursive, scan_zips, compute_hash)
