#!/usr/bin/env python3
"""Generate Python ground-truth vectors for the Rust peer registry (B-d1)."""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sqlite3

from lan_cowork_repo import vectors_dir  # noqa: E402

DDL = (
    "CREATE TABLE peers ("
    "peer_id TEXT PRIMARY KEY, name TEXT, api_host TEXT, api_port INTEGER,"
    "token TEXT, token_expires_at INTEGER, token_issued_at INTEGER,"
    "pubkey BLOB, x25519_pk BLOB,"
    "created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,"
    "last_reached_at INTEGER, last_attempted_at INTEGER)"
)
UPSERT = (
    "INSERT INTO peers (peer_id,name,api_host,api_port,token,token_expires_at,"
    "token_issued_at,pubkey,x25519_pk,created_at,updated_at) "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?) "
    "ON CONFLICT(peer_id) DO UPDATE SET "
    "name=excluded.name, api_host=excluded.api_host, api_port=excluded.api_port,"
    "token=excluded.token, token_expires_at=excluded.token_expires_at,"
    "token_issued_at=excluded.token_issued_at,"
    "pubkey=COALESCE(excluded.pubkey, pubkey),"
    "x25519_pk=COALESCE(excluded.x25519_pk, x25519_pk),"
    "updated_at=excluded.updated_at"
)
COLS = [
    "peer_id", "name", "api_host", "api_port", "token", "token_expires_at",
    "token_issued_at", "pubkey", "x25519_pk", "created_at", "updated_at",
    "last_reached_at", "last_attempted_at",
]


def hx(value):
    return value.hex() if value is not None else None


def blob(value):
    return bytes.fromhex(value) if value else None


def dump(con):
    out = []
    for result in con.execute(f"SELECT {','.join(COLS)} FROM peers ORDER BY peer_id"):
        entry = dict(zip(COLS, result, strict=True))
        entry["pubkey"] = hx(entry["pubkey"])
        entry["x25519_pk"] = hx(entry["x25519_pk"])
        out.append(entry)
    return out


def insert_initial(con, rows):
    for item in rows:
        con.execute(
            f"INSERT INTO peers ({','.join(COLS)}) VALUES ({','.join('?' * len(COLS))})",
            [blob(item[column]) if column in ("pubkey", "x25519_pk") else item[column] for column in COLS],
        )


def upsert_case(label, now, initial, inp):
    con = sqlite3.connect(":memory:")
    con.execute(DDL)
    insert_initial(con, initial)
    con.execute(UPSERT, (
        inp["peer_id"], inp["name"], inp["api_host"], inp["api_port"], inp["token"],
        inp["token_expires_at"], inp["token_issued_at"], blob(inp["pubkey"]),
        blob(inp["x25519_pk"]), now, now,
    ))
    rows = dump(con)
    con.close()
    return {"label": label, "op": "upsert", "now": now, "initial_rows": initial,
            "input": inp, "expected_rows": rows}


PK = "01" * 32
XK = "02" * 32


def peer(peer_id, **kwargs):
    value = {"peer_id": peer_id, "name": "node", "api_host": "10.0.0.2", "api_port": 8188,
             "token": None, "token_expires_at": None, "token_issued_at": None,
             "pubkey": None, "x25519_pk": None}
    value.update(kwargs)
    return value


def row(peer_id, created, updated, **kwargs):
    value = peer(peer_id, **kwargs)
    value.update({"created_at": created, "updated_at": updated,
                  "last_reached_at": kwargs.get("last_reached_at"),
                  "last_attempted_at": kwargs.get("last_attempted_at")})
    return value


def load_all_case(label, hard_cutoff, soft_cutoff, now, local_peer_id, initial):
    con = sqlite3.connect(":memory:")
    con.execute(DDL)
    insert_initial(con, initial)
    con.execute("DELETE FROM peers WHERE (last_reached_at IS NOT NULL AND last_reached_at < ?) "
                "OR (last_reached_at IS NULL AND created_at < ?)", (hard_cutoff, hard_cutoff))
    con.execute("DELETE FROM peers WHERE (token IS NULL OR token = '') "
                "AND last_reached_at IS NULL AND created_at < ?", (soft_cutoff,))
    memory = []
    for result in con.execute("SELECT peer_id,name,api_host,api_port,token,token_expires_at,"
                              "token_issued_at,pubkey,x25519_pk,last_reached_at,last_attempted_at "
                              "FROM peers ORDER BY peer_id"):
        peer_id = result[0]
        if peer_id == local_peer_id:
            con.execute("DELETE FROM peers WHERE peer_id=?", (peer_id,))
            continue
        memory.append({"peer_id": peer_id, "status": "online", "has_pubkey": result[7] is not None})
    rows = dump(con)
    con.close()
    return {"label": label, "op": "load_all", "hard_cutoff": hard_cutoff,
            "soft_cutoff": soft_cutoff, "now": now, "local_peer_id": local_peer_id,
            "initial_rows": initial, "expected_rows": rows, "expected_memory": memory}


def remove_case(label, initial, peer_id):
    con = sqlite3.connect(":memory:")
    con.execute(DDL)
    insert_initial(con, initial)
    con.execute("DELETE FROM peers WHERE peer_id=?", (peer_id,))
    rows = dump(con)
    con.close()
    return {"label": label, "op": "remove", "target": peer_id,
            "initial_rows": initial, "expected_rows": rows}


def telemetry_case(label, initial, peer_id, reached, attempted):
    con = sqlite3.connect(":memory:")
    con.execute(DDL)
    insert_initial(con, initial)
    if reached is not None:
        con.execute("UPDATE peers SET last_reached_at=?, last_attempted_at=?, updated_at=? "
                    "WHERE peer_id=?", (reached, reached, reached, peer_id))
    elif attempted is not None:
        con.execute("UPDATE peers SET last_attempted_at=?, updated_at=? WHERE peer_id=?",
                    (attempted, attempted, peer_id))
    rows = dump(con)
    con.close()
    return {"label": label, "op": "telemetry", "target": peer_id, "reached": reached,
            "attempted": attempted, "initial_rows": initial, "expected_rows": rows}


def main():
    now = 1_700_000_000
    cases = [
        upsert_case("insert_new", now, [], peer("aa" * 16, pubkey=PK, x25519_pk=XK)),
        upsert_case("token_only_update_preserves_keys", now,
                    [row("bb" * 16, created=1, updated=1, pubkey=PK, x25519_pk=XK)],
                    peer("bb" * 16, token="tok", pubkey=None, x25519_pk=None)),
        upsert_case("update_overwrites_present_keys", now,
                    [row("cc" * 16, created=5, updated=5, pubkey=PK, x25519_pk=XK)],
                    peer("cc" * 16, pubkey="03" * 32, x25519_pk="04" * 32)),
    ]
    hard_cutoff, soft_cutoff, now2 = 1_000_000_000, 1_699_996_400, 1_700_000_000
    cases.append(load_all_case("hydrate_prune_self", hard_cutoff, soft_cutoff, now2, "ff" * 16, [
        row("aa" * 16, created=now2 - 10, updated=now2 - 10, last_reached_at=now2 - 10, pubkey=PK),
        row("bb" * 16, created=1, updated=1, last_reached_at=1),
        row("cc" * 16, created=1, updated=1),
        row("ee" * 16, created=1_699_990_000, updated=1_699_990_000),
        row("dd" * 16, created=now2 - 100, updated=now2 - 100, token="t", last_reached_at=None),
        row("ff" * 16, created=now2 - 10, updated=now2 - 10, last_reached_at=now2 - 10),
    ]))
    cases.append(remove_case("remove_existing", [row("aa" * 16, created=1, updated=1, pubkey=PK)], "aa" * 16))
    cases.append(telemetry_case("telemetry_reached", [row("bb" * 16, created=1, updated=1)], "bb" * 16, 1_700_000_500, None))
    cases.append(telemetry_case("telemetry_attempted_only", [row("cc" * 16, created=1, updated=1)], "cc" * 16, None, 1_700_000_600))
    vectors = {"peers_ddl": DDL, "cases": cases}
    out = vectors_dir() / "registry_vectors.json"
    out.write_text(json.dumps(vectors, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
