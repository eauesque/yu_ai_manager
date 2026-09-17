"""API key scope definitions and enforcement.

Scopes restrict which endpoints an API key can access.
Keys without scopes have full access (backward compatible).
"""

from __future__ import annotations

# All valid scope names
VALID_SCOPES = frozenset({
    "read",              # Search, file detail, thumbnail, stats
    "rate",              # Rating set/get/batch
    "tag.write",         # Tag add/remove
    "collection.write",  # Collection create/update/delete, batch-add, favorites
    "annotate",          # Annotation read/write/delete
    "scan",              # Scan start/cancel/resume
    "admin",             # API key management, settings, backup/restore
})

# Path prefix rules for mutation endpoints (POST/PUT/DELETE).
# Format: (path_prefix, required_scope)
# Checked in order; first match wins.
# GET requests always pass (read is implicit for any authenticated key).
_MUTATION_SCOPE_RULES: list[tuple[str, str]] = [
    ("/api/ratings/", "rate"),
    ("/api/tags/", "tag.write"),
    ("/api/collections/", "collection.write"),
    ("/api/favorites/", "collection.write"),
    ("/api/annotations/", "annotate"),
    ("/api/scan/", "scan"),
    ("/api/apikeys", "admin"),
    ("/api/settings/", "admin"),
    ("/api/tools/restore", "admin"),
    ("/api/tools/clear-cache", "admin"),
    ("/api/tools/rebuild-groups", "admin"),
    ("/api/tools/debug-log/clear", "admin"),
]


def validate_scopes(scopes: list) -> str | None:
    """Validate a list of scope strings. Returns error message or None."""
    if not isinstance(scopes, list):
        return "scopes must be an array"
    for s in scopes:
        if not isinstance(s, str) or s not in VALID_SCOPES:
            return f"invalid scope: {s!r}. Valid: {sorted(VALID_SCOPES)}"
    return None


def key_has_scope(key_info: dict, required_scope: str) -> bool:
    """Check if a key has a required scope.

    Keys without scopes are allowed read-only access (safe default).
    Full access requires explicitly granting all scopes.
    """
    scopes = key_info.get("scopes")
    if not scopes:
        # No scopes set = read-only (safe default)
        return required_scope == "read"
    return required_scope in scopes


def get_required_scope(method: str, path: str) -> str | None:
    """Determine the scope required for a given request.

    Returns None if no scope restriction applies (e.g. GET requests).
    """
    if method == "GET":
        return None  # Read is implicit for all authenticated keys
    for prefix, scope in _MUTATION_SCOPE_RULES:
        if path.startswith(prefix):
            return scope
    # Default deny: unregistered mutation endpoints require admin scope
    return "admin"
