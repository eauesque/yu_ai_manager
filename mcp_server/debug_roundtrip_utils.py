"""Shared helpers for roundtrip debug tests."""

import contextlib

from .debug_helpers import _g, _sql


def cleanup_stale_roundtrip_data(client) -> None:
    with contextlib.suppress(Exception):
        client.post("/api/ratings/set", {"file_id": 999999999, "rating": 0})
    with contextlib.suppress(Exception):
        chk = client.get("/api/favorites/check", {"file_id": "1", "collection_id": "1"})
        if _g(chk, "is_favorite", False):
            client.post("/api/favorites/toggle", {"file_id": 1, "collection_id": 1})


def resolve_roundtrip_file_id(client):
    res = _sql(client, "SELECT id FROM files WHERE is_deleted=0 ORDER BY RANDOM() LIMIT 1")
    if not res.get("rows"):
        return None
    return res["rows"][0]["id"]
