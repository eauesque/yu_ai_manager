"""Remote-side endpoints: serve DB metadata and files to importing peers."""
from __future__ import annotations

import asyncio
import pathlib
import tempfile
import zipfile
from typing import Any

from quart import Blueprint, Response, jsonify, request, send_file

from core.web.auth_route_policy import auth_route

_AUTH_PREFIX = "/ext/lan_cowork"
_IN_CHUNK_SIZE = 500


def _chunks(items: list[int], size: int | None = None):
    size = _IN_CHUNK_SIZE if size is None else size
    for start in range(0, len(items), size):
        yield items[start:start + size]


# --- DB query helpers (read-only) ---

def _query_files_full(after_rowid: int | None = None) -> tuple[list[dict], int]:
    from core.services_core.db_state import get_readonly_db
    con = get_readonly_db()
    if after_rowid is None:
        rows = con.execute(
            """SELECT id,path,hash,phash,mtime,size,width,height,meta_source
               FROM files WHERE is_deleted=0 ORDER BY id"""
        ).fetchall()
    else:
        rows = con.execute(
            """SELECT id,path,hash,phash,mtime,size,width,height,meta_source
               FROM files WHERE is_deleted=0 AND id>? ORDER BY id""",
            (after_rowid,),
        ).fetchall()
    result = [dict(r) for r in rows]
    max_rowid = result[-1]["id"] if result else (after_rowid or 0)
    return result, max_rowid


def _redact_file_path(path: str) -> str:
    """Return only the basename for peer-facing metadata payloads."""
    if not isinstance(path, str) or not path:
        return ""
    return pathlib.Path(path).name


def _query_tags(file_ids: list[int]) -> dict[str, list[str]]:
    if not file_ids:
        return {}
    from core.services_core.db_state import get_readonly_db
    con = get_readonly_db()
    result: dict[str, list[str]] = {}
    for chunk in _chunks(list(dict.fromkeys(file_ids))):
        placeholders = ",".join("?" for _ in chunk)
        cursor = con.execute(
            f"""SELECT ft.file_id, t.tag FROM file_tags ft
                JOIN tags t ON ft.tag_id = t.id
                WHERE ft.file_id IN ({placeholders})""",
            chunk,
        )
        for r in cursor:
            result.setdefault(str(r[0]), []).append(r[1])
    return result


def _query_collections() -> list[dict]:
    from core.services_core.db_state import get_readonly_db
    con = get_readonly_db()
    rows = con.execute("SELECT id, name FROM collections").fetchall()
    return [dict(r) for r in rows]


def _query_ratings(file_ids: list[int]) -> dict[str, int]:
    if not file_ids:
        return {}
    from core.services_core.db_state import get_readonly_db
    con = get_readonly_db()
    result: dict[str, int] = {}
    for chunk in _chunks(list(dict.fromkeys(file_ids))):
        placeholders = ",".join("?" for _ in chunk)
        cursor = con.execute(
            f"SELECT file_id, rating FROM file_ratings WHERE file_id IN ({placeholders})",
            chunk,
        )
        result.update({str(r[0]): r[1] for r in cursor})
    return result


def _query_annotations(file_ids: list[int]) -> dict[str, list[dict[str, Any]]]:
    """Return per-file list of annotation rows.

    Schema: file_annotations(file_id, source, key, value BLOB, confidence, created_at).
    BLOB values are decoded as UTF-8 when possible, otherwise base64-encoded.
    """
    if not file_ids:
        return {}
    import base64

    from core.services_core.db_state import get_readonly_db
    con = get_readonly_db()
    result: dict[str, list[dict[str, Any]]] = {}
    for chunk in _chunks(list(dict.fromkeys(file_ids))):
        placeholders = ",".join("?" for _ in chunk)
        cursor = con.execute(
            f"""SELECT file_id, source, key, value, confidence, created_at
                FROM file_annotations WHERE file_id IN ({placeholders})""",
            chunk,
        )
        for r in cursor:
            value = r[3]
            if isinstance(value, (bytes, bytearray)):
                try:
                    value_str = value.decode("utf-8")
                    value_enc = "utf8"
                except UnicodeDecodeError:
                    value_str = base64.b64encode(value).decode("ascii")
                    value_enc = "base64"
            else:
                value_str = value
                value_enc = "utf8"
            result.setdefault(str(r[0]), []).append({
                "source": r[1], "key": r[2],
                "value": value_str, "value_enc": value_enc,
                "confidence": r[4], "created_at": r[5],
            })
    return result


def _query_file_path(file_id: int) -> str | None:
    """Return the file path for *file_id*, or None if not found. Runs in a thread."""
    from core.services_core.db_state import get_readonly_db
    con = get_readonly_db()
    row = con.execute(
        "SELECT path FROM files WHERE id=? AND is_deleted=0", (file_id,)
    ).fetchone()
    return row[0] if row else None


def _open_zip_stream(file_ids: list[int]):
    """Build a ZIP archive for *file_ids* and return a readable stream."""
    from core.services_core.db_state import get_readonly_db
    con = get_readonly_db()
    unique_file_ids = list(dict.fromkeys(file_ids))
    path_by_id: dict[int, str] = {}
    for chunk in _chunks(unique_file_ids):
        placeholders = ",".join("?" for _ in chunk)
        cursor = con.execute(
            f"SELECT id,path FROM files WHERE id IN ({placeholders}) AND is_deleted=0",
            chunk,
        )
        path_by_id.update({int(row["id"]): row["path"] for row in cursor})
    buf = tempfile.SpooledTemporaryFile(max_size=16 * 1024 * 1024, mode="w+b")  # noqa: SIM115 — intentional: file lives beyond context
    count = 0
    try:
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for fid in unique_file_ids:
                path = path_by_id.get(fid)
                if path is None:
                    continue
                p = pathlib.Path(path)
                if p.is_file():
                    zf.write(str(p), arcname=f"{fid}/{p.name}")
                    count += 1
    except Exception:
        buf.close()
        raise
    if count == 0:
        buf.close()
        return None
    buf.seek(0)
    return buf


def _build_meta_response(mode: str, after_rowid: int | None) -> dict[str, Any]:
    files, max_rowid = _query_files_full(after_rowid)
    for f in files:
        f["path"] = _redact_file_path(f.get("path", ""))
    file_ids = [f["id"] for f in files]

    if mode == "index":
        slim = [
            {k: f[k] for k in ("id", "path", "hash", "phash", "size")}
            for f in files
        ]
        return {
            "files": slim,
            "tags": _query_tags(file_ids),
            "max_rowid": max_rowid,
        }

    return {
        "files": files,
        "tags": _query_tags(file_ids),
        "collections": _query_collections(),
        "file_ratings": _query_ratings(file_ids),
        "file_annotations": _query_annotations(file_ids),
        "max_rowid": max_rowid,
    }


def register_routes(bp: Blueprint, get_manager) -> None:
    from ..core_impl.peer_auth import require_peer_auth
    _auth = require_peer_auth(get_manager)

    @auth_route(bp, "/api/peer/import/meta", methods=["GET"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer")
    @_auth
    async def import_meta():
        mode = request.args.get("mode", "full")
        if mode not in ("full", "index"):
            return jsonify({"ok": False, "error": "invalid mode"}), 400
        # Run blocking DB queries off the event loop to avoid freezing the server.
        data = await asyncio.to_thread(_build_meta_response, mode=mode, after_rowid=None)
        return jsonify({"ok": True, **data})

    @auth_route(bp, "/api/peer/import/diff", methods=["GET"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer")
    @_auth
    async def import_diff():
        try:
            after_rowid = int(request.args.get("after_rowid", 0))
        except ValueError:
            after_rowid = 0
        # Run blocking DB queries off the event loop to avoid freezing the server.
        data = await asyncio.to_thread(
            _build_meta_response, mode="full", after_rowid=after_rowid or None
        )
        return jsonify({"ok": True, **data})

    @auth_route(bp, "/api/peer/import/file/<int:file_id>", methods=["GET"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer")
    @_auth
    async def import_file(file_id: int):
        path_str = await asyncio.to_thread(_query_file_path, file_id)
        if path_str is None:
            return jsonify({"ok": False, "error": "file not found"}), 404
        p = pathlib.Path(path_str)
        if not p.is_file():
            return jsonify({"ok": False, "error": "file missing on disk"}), 404
        return await send_file(str(p))

    @auth_route(bp, "/api/peer/import/zip", methods=["GET"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer")
    @_auth
    async def import_zip():
        ids_str = request.args.get("ids", "")
        try:
            file_ids = [int(x) for x in ids_str.split(",") if x.strip()]
        except ValueError:
            return jsonify({"ok": False, "error": "invalid ids"}), 400
        if not file_ids:
            return jsonify({"ok": False, "error": "no ids"}), 400

        # Build ZIP in a thread: DB queries + file I/O are both blocking.
        zip_file = await asyncio.to_thread(_open_zip_stream, file_ids)
        if zip_file is None:
            return jsonify({"ok": False, "error": "no files"}), 404

        async def generate():
            try:
                while True:
                    chunk = await asyncio.to_thread(zip_file.read, 65536)
                    if not chunk:
                        break
                    yield chunk
            finally:
                zip_file.close()

        return Response(
            generate(),
            mimetype="application/zip",
            headers={"Content-Disposition": "attachment; filename=import.zip"},
        )

    @auth_route(bp, "/api/peer/import/stream/<int:file_id>", methods=["GET"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer")
    @_auth
    async def import_stream(file_id: int):
        path_str = await asyncio.to_thread(_query_file_path, file_id)
        if path_str is None:
            return jsonify({"ok": False, "error": "file not found"}), 404
        p = pathlib.Path(path_str)
        if not p.is_file():
            return jsonify({"ok": False, "error": "file missing on disk"}), 404

        async def generate():
            # Every chunk was read on the event loop, so streaming one large
            # file stalled every other request for the length of the transfer.
            handle = await asyncio.to_thread(open, str(p), "rb")
            try:
                while chunk := await asyncio.to_thread(handle.read, 65536):
                    yield chunk
            finally:
                handle.close()

        return Response(generate(), mimetype="application/octet-stream")
