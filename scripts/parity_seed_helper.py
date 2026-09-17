"""Shared DB seed helper for Phase 1 and Phase 3 parity checks."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIXTURE_A1111 = (
    REPO
    / "crates"
    / "meta-extract"
    / "tests"
    / "fixtures"
    / "inspect_parity"
    / "a1111.png"
)
PARITY_COLLECTION_NAME = "parity-test-collection"


# The OCR fixture. Multi-byte on purpose: the export writers slice by
# character, so a byte-slicing port panics or truncates mid-codepoint here
# instead of passing quietly. Two regions -- one with a bbox, one without --
# so both region branches are exercised.
_ONE_PIXEL_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753"
    "de0000000c4944415408d763f8cfc00000030101001839d9b4000000004945"
    "4e44ae426082"
)
# Every other timestamp this helper seeds is the fixed epoch 1700000000. The
# two collection rows used to take `int(time.time())` instead, and the harness
# seeds the Python DB and the Rust DB in separate calls -- so whenever those
# calls straddled a second boundary the two DBs disagreed on created_at, and
# GET /api/collections reported a body difference that belonged to the harness,
# not to either server. Pin it like the rest.
SEED_EPOCH = 1700000000
OCR_FIXTURE_FILE_ID = 9001
OCR_FIXTURE_REGIONS = (
    '[{"region_id":1,"bbox":[10,20,30,40],"text":"\u3053\u3093\u306b\u3061\u306f",'
    '"confidence":0.9,"direction":"horizontal","label":""},'
    '{"region_id":2,"bbox":[],"text":"second line",'
    '"confidence":0.8,"direction":"vertical","label":"note"}]'
)
OCR_FIXTURE_FULL_TEXT = "\u3053\u3093\u306b\u3061\u306f\nsecond line"


def seed_parity_db(db_path: Path) -> dict[str, int]:
    """Create a fresh SQLite DB seeded with a file and a parity collection."""
    import sys

    sys.path.insert(0, str(REPO))
    from core.models_core.models_tags import reset_tag_cache
    from core.scan_core.scanner import scan_one
    from core.schema_core.schema_init import init_db

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        for _ in range(5):
            try:
                db_path.unlink()
                break
            except PermissionError:
                time.sleep(0.5)

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    init_db(con, enable_fts=False)

    # `upsert_tag` memoises tag ids in a process-global dict keyed only by
    # (namespace, tag) -- not by connection. Seeding a second database in the
    # same process therefore reused ids from the first one, writing `file_tags`
    # rows that pointed at `tags` rows this database never got. The parity
    # harness seeds twice (Python's copy, then Rust's), so only the Rust copy
    # was built that way: files=1, file_tags=1, tags=0. The detail route read
    # it faithfully and returned no tags, which read as a Rust bug for as long
    # as the body comparison stayed switched off.
    reset_tag_cache()

    scan_one(con, FIXTURE_A1111, {}, force=True, compute_hash=False)
    file_id: int = con.execute("SELECT id FROM files LIMIT 1").fetchone()["id"]

    if not con.execute("SELECT 1 FROM collections WHERE id=1").fetchone():
        con.execute(
            "INSERT INTO collections (id, name, sort_order, created_at) VALUES (1, 'Favorites', 0, ?)",
            (SEED_EPOCH,),
        )

    con.execute(
        "INSERT INTO collections (name, sort_order, created_at) VALUES (?, 0, ?)",
        (PARITY_COLLECTION_NAME, SEED_EPOCH),
    )
    collection_id: int = con.execute(
        "SELECT id FROM collections WHERE name = ? ORDER BY id DESC LIMIT 1",
        (PARITY_COLLECTION_NAME,),
    ).fetchone()["id"]

    # tag_dict/info parity test requires at least one entry
    con.execute(
        "INSERT OR IGNORE INTO tag_dictionary (tag_name, category, post_count) VALUES ('cat', 4, 500000)",
    )

    # chatlog search parity test requires FTS virtual table
    con.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS chat_messages_fts USING fts5(content, tokenize='unicode61')"
    )

    # Reserved for the read-only OCR entries. file_id=1's result is destroyed
    # mid-suite by `DELETE /api/ocr/result/1`, so anything reading it afterwards
    # compares two different states and calls the difference a port defect.
    #
    # It carries a real `files` row and a real image on disk because the overlay
    # endpoint opens the source image; without them Python answers 404 and the
    # parity entry compares two 404s while rendering nothing.
    #
    # An earlier revision omitted the `files` row, believing it made
    # `POST /api/collections` fail. That was measured and disproved: driving the
    # Python server against two databases differing only in this row gave
    # 201-in-0.00s both ways, and `cleanup_dedupe_paths` (the suspected sweep)
    # runs in 0.00s and changes nothing.
    # NOT `db_path.parent`: the two parity databases live in different
    # directories on purpose, so a path derived from the DB's own location is
    # stored differently in each one, and every endpoint returning this row then
    # reports a difference that no port can close. One shared location means one
    # stored string; both servers run on this machine and can open it.
    fixture_image = REPO / "tmp" / "parity-ocr-fixture.png"
    fixture_image.parent.mkdir(parents=True, exist_ok=True)
    fixture_image.write_bytes(_ONE_PIXEL_PNG)
    con.execute(
        "INSERT OR IGNORE INTO files "
        "(id, path, mtime, size, is_deleted, not_modified, parser_version, "
        " is_zip_member, has_sweep) "
        "VALUES (9001, ?, 1700000000, ?, 0, 0, 0, 0, 0)",
        (str(fixture_image), fixture_image.stat().st_size),
    )
    con.execute(
        "INSERT OR IGNORE INTO file_ocr_results "
        "(id, file_id, engine, task, regions_json, full_text, structured_json, "
        " language, created_at) "
        "VALUES (9001, 9001, 'parity-engine', 'ocr', ?, ?, '{}', 'ja', 1700000000)",
        (
            OCR_FIXTURE_REGIONS,
            OCR_FIXTURE_FULL_TEXT,
        ),
    )

    con.commit()
    con.close()
    return {
        "file_id": file_id,
        "collection_id": collection_id,
        "ocr_file_id": OCR_FIXTURE_FILE_ID,
    }


def seed_ids_from_existing_db(db_path: Path) -> dict[str, int]:
    """Read an already-seeded DB and return known IDs for variable resolution."""
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    file_row = con.execute("SELECT id FROM files LIMIT 1").fetchone()
    coll_row = con.execute(
        "SELECT id FROM collections WHERE name = ? ORDER BY id DESC LIMIT 1",
        (PARITY_COLLECTION_NAME,),
    ).fetchone()
    con.close()
    return {
        "file_id": file_row["id"] if file_row else 0,
        "collection_id": coll_row["id"] if coll_row else 0,
    }
