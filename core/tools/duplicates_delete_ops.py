"""Duplicate deletion helpers."""

from pathlib import Path
from typing import Any

from core.services_core.db_api import get_raw_db


def _mark_deleted_write(targets: list[str]) -> int:
    """Bulk soft-delete on the dedicated DB writer thread."""
    if not targets:
        return 0
    con = get_raw_db()
    con.executemany(
        "UPDATE files SET is_deleted=1 WHERE path=?",
        [(p,) for p in targets],
    )
    con.commit()
    return len(targets)


def delete_duplicates(groups: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    targets: list[str] = []
    for group in groups:
        files = group.get("files", [])
        targets.extend(files[1:])

    errors: list[str] = []

    from core.services_core.db_write import submit_db_write
    try:
        deleted = submit_db_write(_mark_deleted_write, targets)
    except Exception as e:
        return {"deleted": 0, "mode": mode, "errors": [f"db_write_failed: {e}"]}

    if mode == "hard":
        for file_path in targets:
            try:
                p = Path(file_path)
                if p.exists():
                    p.unlink()
            except Exception as e:
                errors.append(f"{file_path}: {str(e)}")

    result: dict[str, Any] = {"deleted": deleted, "mode": mode}
    if errors:
        result["errors"] = errors[:10]
    return result
