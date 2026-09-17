"""Scan error query and management endpoints."""

import sqlite3
from typing import Any

from core.infra_core.api_validation import error_payload
from core.scan_core.scan_errors import (
    clear_resolved_errors,
    get_scan_errors,
    get_unresolved_count,
    resolve_scan_error,
)


def scan_errors_list_payload(
    con: sqlite3.Connection,
    error_type: str = "",
    resolved: str = "",
    limit: int = 200,
) -> tuple[dict[str, Any], int]:
    """GET /api/scan-errors — list scan errors."""
    filt_type = error_type or None
    filt_resolved = None
    if resolved == "true":
        filt_resolved = True
    elif resolved == "false":
        filt_resolved = False

    if limit < 1 or limit > 1000:
        limit = 200

    errors = get_scan_errors(con, error_type=filt_type, resolved=filt_resolved, limit=limit)
    unresolved = get_unresolved_count(con)
    return {
        "errors": errors,
        "total": len(errors),
        "unresolved_count": unresolved,
    }, 200


def scan_errors_resolve_payload(
    con: sqlite3.Connection,
    error_id: int,
) -> tuple[dict[str, Any], int]:
    """POST /api/scan-errors/<id>/resolve — mark error as resolved."""
    if error_id < 1:
        return error_payload("Invalid error_id", "invalid_id", 400)
    found = resolve_scan_error(con, error_id)
    if not found:
        return error_payload("Error not found or already resolved", "not_found", 404)
    con.commit()
    return {"resolved": True, "id": error_id}, 200


def scan_errors_clear_payload(
    con: sqlite3.Connection,
) -> tuple[dict[str, Any], int]:
    """POST /api/scan-errors/clear — delete all resolved errors."""
    deleted = clear_resolved_errors(con)
    con.commit()
    return {"deleted": deleted}, 200
