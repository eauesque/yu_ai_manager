#!/usr/bin/env python3
"""Generate Python ground-truth vectors for the Rust peer read handlers (B-d2)."""
from __future__ import annotations

import base64
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sys

from lan_cowork_repo import vectors_dir  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from extensions.builtin_lan_cowork.core_impl.models import PeerInfo

PK = bytes(range(1, 33))
XK = bytes(range(33, 65))


def make_peer(**kw) -> PeerInfo:
    base = dict(
        name="node-A", api_host="10.0.0.2", api_port=8188, peer_id="aa" * 16,
        version="4.514.0", bridges=["comfyui"], inference_types=["wd"],
        pubkey=PK, x25519_pk=XK, gpu="rtx", generating=False, queue_depth=0,
        status="online", last_seen=1700000000.5, token="tok",
        token_expires_at=1700000600, token_issued_at=1700000000,
        session_id="sess-1", roles=["chief"],
    )
    base.update(kw)
    return PeerInfo(**base)


def raw(peer: PeerInfo) -> dict:
    return {
        "peer_id": peer.peer_id, "name": peer.name, "api_host": peer.api_host,
        "api_port": peer.api_port, "version": peer.version, "bridges": peer.bridges,
        "inference_types": peer.inference_types,
        "pubkey": peer.pubkey.hex() if peer.pubkey else None,
        "x25519_pk": peer.x25519_pk.hex() if peer.x25519_pk else None,
        "gpu": peer.gpu, "generating": peer.generating, "queue_depth": peer.queue_depth,
        "status": peer.status, "last_seen": peer.last_seen, "token": peer.token,
        "token_expires_at": peer.token_expires_at, "token_issued_at": peer.token_issued_at,
        "session_id": peer.session_id, "roles": list(peer.roles),
    }


def serialize_peer(peer: PeerInfo, session_ok: bool, has_inbound_token: bool) -> dict:
    if session_ok:
        d = peer.to_dict()
        d["has_inbound_token"] = has_inbound_token
        return d
    return peer.to_public_dict()


def b64(value):
    return base64.b64encode(value).decode() if value else None


def main() -> None:
    keyed = make_peer()
    no_keys = make_peer(pubkey=None, x25519_pk=None)
    other = make_peer(peer_id="bb" * 16, name="node-B", roles=[])
    local_id = "aa" * 16
    cases = [
        {"op": "to_dict", "peer": raw(keyed), "expected": keyed.to_dict()},
        {"op": "to_dict", "peer": raw(no_keys), "expected": no_keys.to_dict()},
        {"op": "to_public_dict", "peer": raw(keyed), "expected": keyed.to_public_dict()},
        {"op": "to_public_dict", "peer": raw(no_keys), "expected": no_keys.to_public_dict()},
        {"op": "serialize_peer", "peer": raw(keyed), "session_ok": True,
         "has_inbound_token": True, "expected": serialize_peer(keyed, True, True)},
        {"op": "serialize_peer", "peer": raw(keyed), "session_ok": True,
         "has_inbound_token": False, "expected": serialize_peer(keyed, True, False)},
        {"op": "serialize_peer", "peer": raw(keyed), "session_ok": False,
         "has_inbound_token": False, "expected": serialize_peer(keyed, False, False)},
        # session_ok=False must ignore has_inbound_token (public view, flag dropped).
        {"op": "serialize_peer", "peer": raw(keyed), "session_ok": False,
         "has_inbound_token": True, "expected": serialize_peer(keyed, False, True)},
        {"op": "discover", "peers": [raw(keyed), raw(other)], "local_peer_id": local_id,
         "session_ok": True, "has_token_ids": ["bb" * 16],
         "expected": {"ok": True, "peers": [
             serialize_peer(other, True, True),  # keyed==local_id is excluded
         ]}},
        {"op": "discover", "peers": [raw(keyed), raw(other)], "local_peer_id": local_id,
         "session_ok": False, "has_token_ids": [],
         "expected": {"ok": True, "peers": [serialize_peer(other, False, False)]}},
        {"op": "status", "peer": raw(keyed), "session_ok": True, "has_inbound_token": False,
         "expected": {"ok": True, "peer": serialize_peer(keyed, True, False),
                      "pubkey": b64(keyed.pubkey), "x25519_pk": b64(keyed.x25519_pk)}},
        {"op": "status", "peer": raw(no_keys), "session_ok": False, "has_inbound_token": False,
         "expected": {"ok": True, "peer": serialize_peer(no_keys, False, False),
                      "pubkey": None, "x25519_pk": None}},
    ]
    out = vectors_dir() / "peer_read_vectors.json"
    out.write_text(json.dumps({"cases": cases}, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
