#!/usr/bin/env python3
"""Generate Python ground-truth vectors for the Rust HELLO codec."""
from __future__ import annotations

import base64
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sys
from types import SimpleNamespace

from lan_cowork_repo import vectors_dir  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.crypto_identity.hello_packet import (
    FLAG_HAS_SIGNATURE,
    _build_for_test,
    _build_signed_bytes,
    _payload_dict,
)
from core.crypto_identity.identity import derive_peer_id
from core.crypto_identity.keypair import ed25519_pubkey_bytes, x25519_pubkey_bytes

SEED = bytes(range(1, 33))
NOW_REF = 1_700_000_000


def peer(**overrides: object) -> SimpleNamespace:
    values = {
        "peer_id": derive_peer_id(ed25519_pubkey_bytes(SEED)),
        "name": "node-A",
        "api_host": "10.0.0.2",
        "api_port": 8188,
        "version": "4.512.0",
        "bridges": ["comfyui"],
        "inference_types": ["wd"],
        "pubkey": None,
        "x25519_pk": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def peer_dict(value: SimpleNamespace, *, pubkey_present: bool = False, x25519_present: bool = False) -> dict:
    return {
        "peer_id": value.peer_id,
        "name": value.name,
        "api_host": value.api_host,
        "api_port": value.api_port,
        "version": value.version,
        "bridges": value.bridges,
        "inference_types": value.inference_types,
        "pubkey_present": pubkey_present,
        "x25519_present": x25519_present,
    }


def signed_case(label: str, value: SimpleNamespace) -> dict:
    return {
        "label": label,
        "signed": True,
        "ts": NOW_REF,
        "peer": peer_dict(value),
        "packet_hex": _build_for_test(value, SEED, ts=NOW_REF).hex(),
    }


def reject_packet(json_bytes: bytes) -> str:
    return (_build_signed_bytes(FLAG_HAS_SIGNATURE, json_bytes, NOW_REF) + bytes(64)).hex()


def main() -> None:
    pubkey = ed25519_pubkey_bytes(SEED)
    x25519_pk = x25519_pubkey_bytes(SEED)
    basic = peer()
    unsigned = peer(pubkey=pubkey, x25519_pk=x25519_pk)
    unsigned_json = json.dumps(_payload_dict(unsigned, None), separators=(",", ":")).encode()
    build_cases = [
        signed_case("signed_basic", basic),
        {
            "label": "unsigned_basic",
            "signed": False,
            "ts": NOW_REF,
            "peer": peer_dict(unsigned, pubkey_present=True, x25519_present=True),
            "packet_hex": _build_signed_bytes(0, unsigned_json, NOW_REF).hex(),
        },
        signed_case("empty_lists", peer(bridges=[], inference_types=[])),
        signed_case("name_u007f", peer(name="A\x7fB")),
        signed_case("name_bmp", peer(name="日本語")),
        signed_case("name_emoji", peer(name="x😀")),
        signed_case("name_specials", peer(name="a\"b\\c\b\t\n\f\r\x01")),
    ]
    verify_cases = [
        {
            "label": label,
            "packet_ts": timestamp,
            "packet_hex": _build_for_test(basic, SEED, ts=timestamp).hex(),
            "expect": expected,
        }
        for label, timestamp, expected in [
            ("ok", NOW_REF, True),
            ("future_30", NOW_REF + 30, True),
            ("future_90", NOW_REF + 90, False),
            ("past_90", NOW_REF - 90, False),
            ("ts_max", 2**64 - 1, False),
        ]
    ]
    payload = _payload_dict(basic, SEED)
    mismatch = dict(payload, peer_id="0" * 32)
    low_order = dict(payload, x25519_pk=base64.b64encode(bytes(32)).decode())
    missing_pubkey = dict(payload)
    del missing_pubkey["pubkey"]
    missing_x25519 = dict(payload)
    del missing_x25519["x25519_pk"]
    bad_pubkey = dict(payload, pubkey="@@@@")
    null_peer_id = dict(payload, peer_id=None)
    num_peer_id = dict(payload, peer_id=123)
    reject_cases = [
        {"label": "peer_id_mismatch", "packet_hex": reject_packet(json.dumps(mismatch, separators=(",", ":")).encode())},
        {"label": "low_order_x25519", "packet_hex": reject_packet(json.dumps(low_order, separators=(",", ":")).encode())},
        {"label": "non_object_json", "packet_hex": reject_packet(b"[]")},
        {"label": "malformed_json", "packet_hex": reject_packet(b"{")},
        {"label": "missing_pubkey", "packet_hex": reject_packet(json.dumps(missing_pubkey, separators=(",", ":")).encode())},
        {"label": "missing_x25519_pk", "packet_hex": reject_packet(json.dumps(missing_x25519, separators=(",", ":")).encode())},
        {"label": "bad_base64_pubkey", "packet_hex": reject_packet(json.dumps(bad_pubkey, separators=(",", ":")).encode())},
        {"label": "null_peer_id", "packet_hex": reject_packet(json.dumps(null_peer_id, separators=(",", ":")).encode())},
        {"label": "num_peer_id", "packet_hex": reject_packet(json.dumps(num_peer_id, separators=(",", ":")).encode())},
    ]
    vectors = {
        "seed_hex": SEED.hex(),
        "pubkey_hex": pubkey.hex(),
        "x25519_pk_hex": x25519_pk.hex(),
        "peer_id": derive_peer_id(pubkey),
        "now_ref": NOW_REF,
        "build_cases": build_cases,
        "verify_cases": verify_cases,
        "reject_cases": reject_cases,
    }
    out = vectors_dir() / "hello_packet_vectors.json"
    out.write_text(json.dumps(vectors, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
