"""Vector DB CRUD for semantic search embeddings.

Stores float16 vectors as BLOBs in vectors.db (separate encrypted DB).
All public functions accept and return float32 arrays; float16 conversion
is transparent to callers.
"""

import logging

import numpy as np

from core.services_core.db_api import get_readonly_db, get_vectors_db, get_vectors_readonly_db
from core.services_core.db_write import submit_db_write

from .vector_store_support import (
    ensure_clip_eligible_files_table,
    get_batch_vectors_con,
)

logger = logging.getLogger(__name__)

# Multiplier for candidate window in cross-DB unindexed queries.
# 8x compensates for high indexed ratio when indexing is near-complete.
_UNINDEXED_WINDOW_MULTIPLIER = 8

# Chunk size for IN queries to stay below conservative SQLite variable limits.
_IN_CHUNK_SIZE = 500


def _chunks(items: list, size: int | None = None):
    size = _IN_CHUNK_SIZE if size is None else size
    for start in range(0, len(items), size):
        yield items[start:start + size]


def save_vector(
    file_id: int,
    vector: np.ndarray,
    model: str = "clip_vit_b_16",
) -> None:
    """Save or update a vector for a file (UPSERT). Stores as float16."""
    blob = vector.astype(np.float16).tobytes()

    def _write() -> None:
        con = get_vectors_db()
        con.execute(
            "INSERT INTO file_vectors (file_id, model, vector) VALUES (?, ?, ?)"
            " ON CONFLICT(file_id) DO UPDATE SET model=excluded.model,"
            " vector=excluded.vector, created_at=strftime('%s','now')",
            (file_id, model, blob),
        )
        con.commit()

    submit_db_write(_write)


def save_vectors_batch(
    file_ids: list,
    vectors: np.ndarray,
    model: str = "clip_vit_b_16",
) -> int:
    """Batch save vectors as float16. Uses dedicated connection with long busy_timeout."""
    vecs_f16 = vectors.astype(np.float16)
    rows = [(fid, model, vecs_f16[i].tobytes()) for i, fid in enumerate(file_ids)]

    def _write() -> int:
        con = get_batch_vectors_con()
        con.execute("BEGIN IMMEDIATE")
        try:
            con.executemany(
                "INSERT INTO file_vectors (file_id, model, vector) VALUES (?, ?, ?)"
                " ON CONFLICT(file_id) DO UPDATE SET model=excluded.model,"
                " vector=excluded.vector, created_at=strftime('%s','now')",
                rows,
            )
            con.commit()
        except Exception:
            con.rollback()
            raise
        return len(rows)

    return submit_db_write(_write)


def load_vector(file_id: int) -> np.ndarray | None:
    """Load a single vector by file_id. Returns float32 or None if not found."""
    con = get_vectors_readonly_db()
    row = con.execute(
        "SELECT vector FROM file_vectors WHERE file_id = ?", (file_id,)
    ).fetchone()
    if row is None:
        return None
    return np.frombuffer(row[0], dtype=np.float16).astype(np.float32)


def load_all_vectors(
    model: str = "clip_vit_b_16",
) -> tuple[np.ndarray, list]:
    """Load all vectors for a model. Returns (float32 array N x dim, file_ids list).

    Excludes deleted files by querying tags.db in chunks to stay within
    SQLite's SQLITE_MAX_VARIABLE_NUMBER limit.
    """
    vec_con = get_vectors_readonly_db()
    rows = vec_con.execute(
        "SELECT file_id, vector FROM file_vectors WHERE model = ?",
        (model,),
    ).fetchall()
    if not rows:
        return np.empty((0, 512), dtype=np.float32), []

    all_fids = [row[0] for row in rows]
    tags_con = get_readonly_db()
    active_ids: set = set()
    for chunk in _chunks(all_fids):
        placeholders = ",".join("?" for _ in chunk)
        active_ids.update(
            r[0] for r in tags_con.execute(
                f"SELECT id FROM files WHERE id IN ({placeholders}) AND is_deleted = 0",  # noqa: S608
                chunk,
            )
        )

    file_ids = []
    vecs = []
    for row in rows:
        fid = row[0]
        if fid not in active_ids:
            continue
        file_ids.append(fid)
        vecs.append(np.frombuffer(row[1], dtype=np.float16).astype(np.float32))

    if not vecs:
        return np.empty((0, 512), dtype=np.float32), []
    return np.stack(vecs), file_ids


def count_indexed(model: str = "clip_vit_b_16") -> int:
    """Count files with vectors (from vectors.db)."""
    con = get_vectors_readonly_db()
    row = con.execute(
        "SELECT COUNT(*) FROM file_vectors WHERE model = ?", (model,)
    ).fetchone()
    return row[0] if row else 0


def count_unindexed(model: str = "clip_vit_b_16") -> int:
    """Count CLIP-eligible files without vectors (eligible minus indexed)."""
    tags_con = get_readonly_db()
    ensure_clip_eligible_files_table(tags_con)
    eligible = tags_con.execute("SELECT COUNT(*) FROM clip_eligible_files").fetchone()[0]
    indexed = count_indexed(model)
    return max(0, eligible - indexed)


def get_unindexed_file_ids(
    model: str = "clip_vit_b_16",
    limit: int = 0,
    exclude_ids: set | None = None,
) -> list:
    """Get file IDs that don't have vectors yet.

    Queries clip_eligible_files (tags.db) and filters out indexed IDs (vectors.db).
    """
    if limit > 0:
        result = get_unindexed_file_ids_cursor(model=model, after_id=0, limit=limit)
    else:
        result = []
        after_id = 0
        while True:
            page = get_unindexed_file_ids_cursor(
                model=model,
                after_id=after_id,
                limit=4000,
            )
            if not page:
                break
            result.extend(page)
            after_id = page[-1]
    if exclude_ids:
        result = [fid for fid in result if fid not in exclude_ids]
    if limit > 0:
        result = result[:limit]
    return result


def get_unindexed_file_ids_cursor(
    model: str = "clip_vit_b_16",
    after_id: int = 0,
    limit: int = 2000,
) -> list:
    """Get unindexed file IDs using cursor pagination (O(1) per page).

    Fetches a window of CLIP-eligible candidates from tags.db, then filters
    out already-indexed IDs by querying the same range in vectors.db.
    Loops forward if the entire window is indexed to avoid missing unindexed
    files that appear later in the ID space.
    """
    tags_con = get_readonly_db()
    ensure_clip_eligible_files_table(tags_con)
    vec_con = get_vectors_readonly_db()

    current_after_id = after_id
    while True:
        window = max(limit * _UNINDEXED_WINDOW_MULTIPLIER, 4000)
        candidates = [
            r[0] for r in tags_con.execute(
                "SELECT file_id FROM clip_eligible_files"
                " WHERE file_id > ? ORDER BY file_id LIMIT ?",
                (current_after_id, window),
            ).fetchall()
        ]
        if not candidates:
            return []

        max_id = candidates[-1]
        indexed = {r[0] for r in vec_con.execute(
            "SELECT file_id FROM file_vectors"
            " WHERE model=? AND file_id > ? AND file_id <= ?",
            (model, current_after_id, max_id),
        ).fetchall()}

        result = [fid for fid in candidates if fid not in indexed][:limit]
        if result:
            return result

        # Entire window was indexed — advance cursor and try next window
        current_after_id = max_id


def get_file_paths_by_ids(file_ids: list) -> dict:
    """Get {file_id: path} mapping for given IDs (queries tags.db files table)."""
    if not file_ids:
        return {}
    con = get_readonly_db()
    paths: dict[int, str] = {}
    for chunk in _chunks(list(dict.fromkeys(file_ids))):
        placeholders = ",".join("?" for _ in chunk)
        cursor = con.execute(
            f"SELECT id, path FROM files WHERE id IN ({placeholders})",  # noqa: S608
            chunk,
        )
        paths.update({int(r[0]): r[1] for r in cursor})
    return paths


def delete_vectors(file_ids: list) -> int:
    """Delete vectors for given file IDs. Returns count deleted."""
    if not file_ids:
        return 0

    def _write() -> int:
        con = get_vectors_db()
        deleted = 0
        for chunk in _chunks(list(dict.fromkeys(file_ids))):
            placeholders = ",".join("?" for _ in chunk)
            cursor = con.execute(
                f"DELETE FROM file_vectors WHERE file_id IN ({placeholders})",  # noqa: S608
                chunk,
            )
            deleted += cursor.rowcount
        con.commit()
        return deleted

    return submit_db_write(_write)


def delete_all_vectors(model: str = "clip_vit_b_16") -> int:
    """Delete all vectors for a model. Returns count deleted."""
    def _write() -> int:
        con = get_vectors_db()
        cursor = con.execute(
            "DELETE FROM file_vectors WHERE model = ?", (model,)
        )
        con.commit()
        return cursor.rowcount

    return submit_db_write(_write)
