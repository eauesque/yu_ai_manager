"""Tag normalize API operations."""

from typing import Any

from core.cleanup_core.cleanup import cleanup_normalize_tags, normalize_tag_string
from core.services_core.db_api import get_raw_db, get_readonly_db


def _normalize_tags_write() -> int:
    """Bulk normalize on the dedicated DB writer thread."""
    con = get_raw_db()
    return cleanup_normalize_tags(con, dry_run=False)


def normalize_tags_api(dry_run: bool) -> dict[str, Any]:
    if dry_run:
        ro = get_readonly_db()
        changes = []
        for row in ro.execute("SELECT DISTINCT tag FROM tags"):
            tag = row[0]
            normalized = normalize_tag_string(tag)
            if tag != normalized:
                changes.append({"before": tag, "after": normalized})
        return {"changes": len(changes), "examples": changes[:20]}

    from core.services_core.db_write import submit_db_write
    normalized = submit_db_write(_normalize_tags_write)
    return {"normalized": normalized}
