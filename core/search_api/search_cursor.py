"""Opaque cursor encoding/decoding for keyset pagination."""

import base64
import json
from typing import Any

# Sorts that support keyset pagination
_KEYSET_SORTS = {"date", "date_new", "date_old", "rating_desc", "rating_asc", "path"}


def encode_cursor(sort_by: str, last_row: dict[str, Any], offset: int) -> str:
    """Encode pagination state into an opaque cursor string.

    last_row: {"mtime": int, "id": int, "path": str, "rating": int|None}
    """
    if sort_by in ("date", "date_new", "date_old"):
        data = {"s": sort_by, "m": last_row["mtime"], "i": last_row["id"]}
    elif sort_by in ("rating_desc", "rating_asc"):
        data: dict = {"s": sort_by, "m": last_row["mtime"], "i": last_row["id"]}
        # rating can be None -- preserve as JSON null
        data["r"] = last_row.get("rating")
    elif sort_by == "path":
        data = {"s": sort_by, "p": last_row.get("path", ""), "i": last_row["id"]}
    else:
        data = {"s": sort_by, "o": offset}
    return base64.urlsafe_b64encode(
        json.dumps(data, separators=(",", ":")).encode()
    ).decode().rstrip("=")


def decode_cursor(cursor_str: str) -> dict | None:
    """Decode an opaque cursor string. Returns None on invalid input."""
    if not cursor_str:
        return None
    try:
        padded = cursor_str + "=" * (-len(cursor_str) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded))
        if not isinstance(data, dict) or "s" not in data:
            return None
        return data
    except Exception:
        return None


def cursor_to_keyset(cursor_data: dict) -> dict | None:
    """Extract keyset values from cursor data.

    Returns a dict with keyset info, or None for offset-based cursors.
    Returned dict keys:
      - "type": "date" | "rating" | "path"
      - "direction": "asc" | "desc"
      - For date: "mtime", "id"
      - For rating: "rating" (int|None), "mtime", "id"
      - For path: "path", "id"
    """
    sort_by = cursor_data.get("s", "")

    if sort_by in ("date", "date_new", "date_old"):
        mtime = cursor_data.get("m")
        file_id = cursor_data.get("i")
        if not isinstance(mtime, int) or not isinstance(file_id, int):
            return None
        direction = "asc" if sort_by == "date_old" else "desc"
        return {"type": "date", "direction": direction,
                "mtime": mtime, "id": file_id}

    if sort_by in ("rating_desc", "rating_asc"):
        mtime = cursor_data.get("m")
        file_id = cursor_data.get("i")
        rating = cursor_data.get("r")  # int or None
        if not isinstance(mtime, int) or not isinstance(file_id, int):
            return None
        direction = "desc" if sort_by == "rating_desc" else "asc"
        return {"type": "rating", "direction": direction,
                "rating": rating, "mtime": mtime, "id": file_id}

    if sort_by == "path":
        path = cursor_data.get("p")
        file_id = cursor_data.get("i")
        if not isinstance(path, str) or not isinstance(file_id, int):
            return None
        return {"type": "path", "direction": "asc",
                "path": path, "id": file_id}

    return None


def cursor_to_offset(cursor_data: dict) -> int:
    """Extract offset from an offset-based cursor. Returns 0 if not present."""
    return cursor_data.get("o", 0)
