"""Favorites & Collections data access layer (Store pattern).

Handles SQL only; does not contain business logic or event emission.
"""

from __future__ import annotations

from typing import Any

from core.services_core.db_state import get_db, get_readonly_db
from core.services_core.db_write import submit_db_write

_IN_CHUNK_SIZE = 500


def _chunks(values: list[int], size: int | None = None):
    size = _IN_CHUNK_SIZE if size is None else size
    for start in range(0, len(values), size):
        yield values[start:start + size]


def find_favorite(file_id: int, collection_id: int) -> bool:
    """Check if a favorite entry exists."""
    con = get_readonly_db()
    row = con.execute(
        "SELECT file_id FROM favorites WHERE file_id=? AND collection_id=?",
        (file_id, collection_id),
    ).fetchone()
    return row is not None


def insert_favorite(file_id: int, collection_id: int) -> None:
    """Add a favorite."""
    from core.services_core.favorites_write_service import insert_favorite_row

    submit_db_write(
        lambda: insert_favorite_row(file_id, collection_id, get_db_fn=get_db)
    )


def delete_favorite(file_id: int, collection_id: int) -> None:
    """Remove a favorite."""
    from core.services_core.favorites_write_service import delete_favorite_row

    submit_db_write(
        lambda: delete_favorite_row(file_id, collection_id, get_db_fn=get_db)
    )


def check_favorites_rows(
    file_ids: list[int], collection_id: int | None = None
) -> list[int]:
    """Return the list of favorited file_ids."""
    if not file_ids:
        return []
    con = get_readonly_db()
    out: set[int] = set()
    if collection_id is not None:
        for chunk in _chunks(file_ids):
            placeholders = ",".join("?" * len(chunk))
            rows = con.execute(
                f"SELECT file_id FROM favorites WHERE file_id IN ({placeholders}) AND collection_id=?",
                list(chunk) + [collection_id],
            )
            out.update(r[0] for r in rows)
    else:
        for chunk in _chunks(file_ids):
            placeholders = ",".join("?" * len(chunk))
            rows = con.execute(
                f"SELECT DISTINCT file_id FROM favorites WHERE file_id IN ({placeholders})",
                chunk,
            )
            out.update(r[0] for r in rows)
    return [fid for fid in file_ids if fid in out]


def get_collections_for_file(file_id: int) -> list[int]:
    """Return the list of collection IDs that contain the file."""
    con = get_readonly_db()
    rows = con.execute(
        "SELECT collection_id FROM favorites WHERE file_id=? ORDER BY collection_id",
        (file_id,),
    )
    return [r[0] for r in rows]


def get_existing_file_ids(file_ids: list[int]) -> list[int]:
    """Return existing, non-deleted file IDs from the files table."""
    if not file_ids:
        return []
    con = get_readonly_db()
    existing: set[int] = set()
    for chunk in _chunks(file_ids):
        placeholders = ",".join("?" * len(chunk))
        rows = con.execute(
            f"SELECT id FROM files WHERE id IN ({placeholders}) AND is_deleted=0",
            chunk,
        )
        existing.update(r[0] for r in rows)
    return [fid for fid in file_ids if fid in existing]


def list_favorite_ids(collection_id: int | None = None) -> list[int]:
    """Return the list of favorite file_ids."""
    con = get_readonly_db()
    if collection_id is not None:
        rows = con.execute(
            "SELECT fav.file_id FROM favorites fav "
            "JOIN files f ON f.id=fav.file_id AND f.is_deleted=0 "
            "WHERE fav.collection_id=? ORDER BY fav.added_at DESC, fav.file_id DESC",
            (collection_id,),
        )
    else:
        rows = con.execute(
            "SELECT fav.file_id, MAX(fav.added_at) AS added_at FROM favorites fav "
            "JOIN files f ON f.id=fav.file_id AND f.is_deleted=0 "
            "GROUP BY fav.file_id "
            "ORDER BY added_at DESC, fav.file_id DESC"
        )
    return [r[0] for r in rows]


def batch_insert_favorites(file_ids: list[int], collection_id: int) -> int:
    """Batch insert multiple favorites. Returns insert count."""
    if not file_ids:
        return 0

    from core.services_core.favorites_write_service import batch_insert_favorite_rows

    return submit_db_write(
        lambda: batch_insert_favorite_rows(
            file_ids, collection_id, get_db_fn=get_db
        )
    )


def batch_delete_favorites(
    file_ids: list[int], collection_id: int | None = None
) -> int:
    """Batch delete multiple favorites. Returns delete count."""
    if not file_ids:
        return 0

    from core.services_core.favorites_write_service import batch_delete_favorite_rows

    return submit_db_write(
        lambda: batch_delete_favorite_rows(
            file_ids, collection_id, get_db_fn=get_db
        )
    )


def get_favorite_paths(
    collection_id: int | None = None,
) -> list[tuple[int, str]]:
    """Return the list of (file_id, path) tuples for favorites."""
    con = get_readonly_db()
    if collection_id is not None:
        rows = con.execute(
            "SELECT f.id, f.path FROM favorites fav "
            "JOIN files f ON f.id=fav.file_id AND f.is_deleted=0 "
            "WHERE fav.collection_id=? ORDER BY fav.added_at DESC, fav.file_id DESC",
            (collection_id,),
        )
    else:
        rows = con.execute(
            "SELECT DISTINCT f.id, f.path FROM favorites fav "
            "JOIN files f ON f.id=fav.file_id AND f.is_deleted=0 "
            "ORDER BY fav.added_at DESC, fav.file_id DESC"
        )
    return [(r[0], r[1]) for r in rows]


def list_collections_rows() -> list[dict[str, Any]]:
    """Return all collections with counts."""
    con = get_readonly_db()
    rows = con.execute(
        "SELECT c.id, c.name, c.sort_order, c.created_at, "
        "COUNT(fav.file_id) AS count, c.query_json "
        "FROM collections c "
        "LEFT JOIN favorites fav ON fav.collection_id=c.id "
        "GROUP BY c.id ORDER BY c.sort_order, c.id"
    )
    return [
        {
            "id": r[0], "name": r[1], "sort_order": r[2],
            "created_at": r[3], "count": r[4],
            "is_smart": r[5] is not None, "query_json": r[5],
        }
        for r in rows
    ]


def insert_collection(name: str, query_json: str | None = None) -> int:
    """Create a collection and return its ID."""
    from core.services_core.favorites_write_service import insert_collection_row

    return submit_db_write(
        lambda: insert_collection_row(name, query_json, get_db_fn=get_db)
    )


def update_collection_name(collection_id: int, name: str) -> None:
    """Update the collection name."""
    from core.services_core.favorites_write_service import update_collection_name_row

    submit_db_write(
        lambda: update_collection_name_row(collection_id, name, get_db_fn=get_db)
    )


def delete_collection_rows(collection_id: int) -> None:
    """Delete a collection and its favorites."""
    from core.services_core.favorites_write_service import delete_collection_row

    submit_db_write(
        lambda: delete_collection_row(collection_id, get_db_fn=get_db)
    )


def reorder_collections_rows(ids: list[int]) -> None:
    """Update the sort_order of collections."""
    from core.services_core.favorites_write_service import reorder_collection_rows

    submit_db_write(
        lambda: reorder_collection_rows(ids, get_db_fn=get_db)
    )


def collection_exists(collection_id: int) -> bool:
    """Check if a collection exists."""
    con = get_readonly_db()
    row = con.execute("SELECT id FROM collections WHERE id=?", (collection_id,)).fetchone()
    return row is not None


def get_collection_name_row(collection_id: int) -> str | None:
    """Return the collection name. Returns None if not found."""
    con = get_readonly_db()
    row = con.execute(
        "SELECT name FROM collections WHERE id=?", (collection_id,)
    ).fetchone()
    return row[0] if row else None
