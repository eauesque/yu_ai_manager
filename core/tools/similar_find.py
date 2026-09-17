"""Find images similar to a specific file by pHash hamming distance.

Uses fetchmany() for chunked processing and terminates early once enough candidates are found.
"""


from core.services_core.db_api import get_readonly_db
from core.tools.helpers_phash_group import hamming_distance_hex

# Chunk size: number of rows fetched from DB at once
_FETCH_CHUNK = 1000


def find_similar_to(
    file_id: int, threshold: int = 5, max_results: int = 50
) -> dict:
    """Find files similar to the given file_id by pHash.

    Processes incrementally with fetchmany() and terminates early once enough
    matches within the threshold are found, reducing memory usage.

    Args:
        file_id: ID of the reference file.
        threshold: Maximum hamming distance (values at or below are considered similar).
        max_results: Maximum number of results to return (internally collects up to 2x before selecting top results).

    Returns:
        dict with "results" key (list sorted by distance ascending):
          {"results": [{id, path, distance, mtime}, ...]}

        Returns {"error": ..., "message": ...} if the file does not exist.
        Returns {"results": []} if the file has no phash or no similar files found.
    """
    con = get_readonly_db()
    # Get the target file's phash
    target = con.execute(
        "SELECT phash FROM files WHERE id=? AND is_deleted=0", (file_id,)
    ).fetchone()
    if not target:
        return {"error": "not_found", "message": f"File {file_id} not found"}
    if not target[0]:
        return {"results": []}

    target_phash = target[0]

    # Chunk processing: fetch incrementally with fetchmany() for early termination
    cursor = con.execute(
        "SELECT id, path, phash, mtime FROM files "
        "WHERE phash IS NOT NULL AND phash != '' AND id != ? AND is_deleted=0",
        (file_id,),
    )

    # Stop once enough candidates are collected (return top max_results)
    collect_limit = max_results * 2
    results: list[dict] = []

    while True:
        rows = cursor.fetchmany(_FETCH_CHUNK)
        if not rows:
            break
        for row in rows:
            dist = hamming_distance_hex(target_phash, row[2])
            if dist <= threshold:
                results.append({
                    "id": row[0],
                    "path": row[1],
                    "distance": dist,
                    "mtime": row[3],
                })
        if len(results) >= collect_limit:
            break

    results.sort(key=lambda r: r["distance"])
    return {"results": results[:max_results]}
    # pooled connection: do not close
