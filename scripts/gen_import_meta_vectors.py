#!/usr/bin/env python3
"""Generate Python ground-truth vectors for LAN Cowork import metadata."""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sqlite3

from lan_cowork_repo import vectors_dir  # noqa: E402

DDL = """
CREATE TABLE files (id INTEGER, path TEXT, hash TEXT, phash TEXT, mtime INTEGER, size INTEGER, width INTEGER, height INTEGER, meta_source TEXT, is_deleted INTEGER);
CREATE TABLE tags (id INTEGER, tag TEXT);
CREATE TABLE file_tags (file_id INTEGER, tag_id INTEGER);
CREATE TABLE collections (id INTEGER, name TEXT);
CREATE TABLE file_ratings (file_id INTEGER, rating);
CREATE TABLE file_annotations (file_id INTEGER, source TEXT, key TEXT, value, confidence, created_at);
"""


def chunks(items: list[int], size: int = 500):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def unique(items: list[int]) -> list[int]:
    return list(dict.fromkeys(items))


def query_files_full(con: sqlite3.Connection, after_rowid: int | None):
    sql = "SELECT id,path,hash,phash,mtime,size,width,height,meta_source FROM files WHERE is_deleted=0"
    args = () if after_rowid is None else (after_rowid,)
    if after_rowid is not None:
        sql += " AND id>?"
    result = [dict(row) for row in con.execute(sql + " ORDER BY id", args)]
    return result, result[-1]["id"] if result else (after_rowid or 0)


def query_tags(con: sqlite3.Connection, file_ids: list[int]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for chunk in chunks(unique(file_ids)):
        placeholders = ",".join("?" for _ in chunk)
        for row in con.execute(f"SELECT ft.file_id,t.tag FROM file_tags ft JOIN tags t ON ft.tag_id=t.id WHERE ft.file_id IN ({placeholders})", chunk):
            result.setdefault(str(row[0]), []).append(row[1])
    return result


def build_meta_response(con: sqlite3.Connection, mode: str, after_rowid: int | None) -> dict:
    files, max_rowid = query_files_full(con, after_rowid)
    for file in files:
        file["path"] = pathlib.Path(file["path"]).name
    file_ids = [file["id"] for file in files]
    if mode == "index":
        return {"files": [{key: file[key] for key in ("id", "path", "hash", "phash", "size")} for file in files], "tags": query_tags(con, file_ids), "max_rowid": max_rowid}
    placeholders = ",".join("?" for _ in file_ids)
    ratings = {str(row[0]): row[1] for row in con.execute(f"SELECT file_id,rating FROM file_ratings WHERE file_id IN ({placeholders})", file_ids)}
    annotations: dict[str, list[dict]] = {}
    for row in con.execute(f"SELECT file_id,source,key,value,confidence,created_at FROM file_annotations WHERE file_id IN ({placeholders})", file_ids):
        annotations.setdefault(str(row[0]), []).append({"source": row[1], "key": row[2], "value": row[3], "value_enc": "utf8", "confidence": row[4], "created_at": row[5]})
    return {"files": files, "tags": query_tags(con, file_ids), "collections": [dict(row) for row in con.execute("SELECT id,name FROM collections")], "file_ratings": ratings, "file_annotations": annotations, "max_rowid": max_rowid}


def main() -> None:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(DDL)
    con.executescript("""
        INSERT INTO files VALUES (1,'/fixture-parent/alpha.png','h1','p1',10,100,20,30,'scan',0),(2,'/fixture-parent/beta.jpg','h2','p2',11,200,40,50,'scan',0),(3,'/fixture-parent/deleted.png','h3','p3',12,300,60,70,'scan',1);
        INSERT INTO tags VALUES (1,'cat'),(2,'dog');
        INSERT INTO file_tags VALUES (1,1),(2,2);
        INSERT INTO collections VALUES (9,'fixture set');
        INSERT INTO file_ratings VALUES (1,3);
        INSERT INTO file_annotations VALUES (1,'fixture','caption','hello',1,99);
    """)
    out = vectors_dir() / "import_meta_vectors.json"
    out.write_text(json.dumps({"expected": {mode: build_meta_response(con, mode, None) for mode in ("index", "full")}}, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
