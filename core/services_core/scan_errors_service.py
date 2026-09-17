"""Synchronous helpers for scan error management routes."""

from __future__ import annotations

from core.infra_core.api_validation import error_payload
from core.scan_core.scan_errors import clear_resolved_errors, resolve_scan_error


def resolve_scan_error_entry(error_id: int):
    from core.services_core.db_api import get_db

    if error_id < 1:
        return error_payload("Invalid error_id", "invalid_id", 400)

    con = get_db()
    found = resolve_scan_error(con, error_id)
    if not found:
        return error_payload("Error not found or already resolved", "not_found", 404)
    con.commit()
    return {"resolved": True, "id": error_id}, 200


def clear_resolved_scan_errors():
    from core.services_core.db_api import get_db

    con = get_db()
    deleted = clear_resolved_errors(con)
    con.commit()
    return {"deleted": deleted}, 200
