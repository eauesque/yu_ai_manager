"""HELLO packet (VERSION=2) build / parse / sign / verify.

Packet layout:
  Offset   Size  Content
  0        4     MAGIC = b"YUAI"
  4        2     VERSION = 2 (big-endian)
  6        2     FLAGS (bit0: has_signature)
  8        4     JSON_LEN (big-endian)
  12       N     JSON payload (UTF-8)
  12+N     8     TIMESTAMP (Unix seconds, big-endian)
  12+N+8   64    Ed25519 signature (only if has_signature=1)

Signature covers data[0 : 12+N+8] (header + json + timestamp) as raw bytes.
"""
from __future__ import annotations

import base64
import json
import struct
import time
from dataclasses import dataclass
from typing import Any

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey

from .identity import assert_peer_id_matches_pubkey
from .keypair import (
    ed25519_pubkey_bytes,
    sign,
    verify,
    x25519_pubkey_bytes,
)

MAGIC = b"YUAI"
VERSION = 2
FLAG_HAS_SIGNATURE = 0x0001
HELLO_TIMESTAMP_TOLERANCE = 60  # seconds

_HEADER_LEN = 12  # MAGIC(4) + VERSION(2) + FLAGS(2) + JSON_LEN(4)
_TS_LEN = 8
_SIG_LEN = 64
_X25519_LOW_ORDER_POINTS = {
    bytes.fromhex(h)
    for h in [
        "0000000000000000000000000000000000000000000000000000000000000000",
        "0100000000000000000000000000000000000000000000000000000000000000",
        "e0eb7a7c3b41b8ae1656e3faf19fc46ada098deb9c32b1fd866205165f49b800",
        "5f9c95bca3508c24b1d0b1559c83ef5b04445cc4581c8e86d8224eddd09f1157",
        "ecffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff7f",
        "edffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff7f",
        "eeffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff7f",
        "cdeb7a7c3b41b8ae1656e3faf19fc46ada098deb9c32b1fd866205165f49b880",
        "4c9c95bca3508c24b1d0b1559c83ef5b04445cc4581c8e86d8224eddd09f11d7",
        # 2p-1 / 2p / 2p+1 (mod 2^256), little-endian: 0xd9/0xda/0xdb followed by
        # 0xff x31. These were previously written with a trailing "7f" copied from
        # the p-1/p/p+1 family above, making them 33 bytes — and therefore dead
        # entries that could never match a length-validated 32-byte key. The
        # 0xdb variant was missing entirely, leaving effective coverage at 9/12.
        "d9ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
        "daffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
        "dbffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
    ]
}


@dataclass
class ParsedHello:
    peer_dict: dict[str, Any]
    pubkey: bytes            # ed25519 pubkey 32B
    x25519_pk: bytes         # x25519 pubkey 32B
    timestamp: int
    signature: bytes | None  # 64B or None
    raw_signed: bytes        # bytes the signature is computed over


def _build_signed_bytes(flags: int, json_bytes: bytes, ts: int) -> bytes:
    header = MAGIC
    header += struct.pack(">H", VERSION)
    header += struct.pack(">H", flags)
    header += struct.pack(">I", len(json_bytes))
    return header + json_bytes + struct.pack(">Q", ts)


def _payload_dict(peer_info: Any, seed: bytes | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "peer_id": peer_info.peer_id,
        "name": peer_info.name,
        "api_host": peer_info.api_host,
        "api_port": peer_info.api_port,
        "version": peer_info.version,
        "bridges": list(peer_info.bridges or []),
        "inference_types": list(peer_info.inference_types or []),
    }
    if seed is not None:
        pubkey = ed25519_pubkey_bytes(seed)
        x25519_pk = x25519_pubkey_bytes(seed)
        payload["pubkey"] = base64.b64encode(pubkey).decode()
        payload["x25519_pk"] = base64.b64encode(x25519_pk).decode()
    else:
        if getattr(peer_info, "pubkey", None):
            payload["pubkey"] = base64.b64encode(peer_info.pubkey).decode()
        if getattr(peer_info, "x25519_pk", None):
            payload["x25519_pk"] = base64.b64encode(peer_info.x25519_pk).decode()
    return payload


def build_hello_packet(peer_info: Any, seed: bytes | None) -> bytes:
    """Build a VERSION=2 HELLO packet. Signed when seed is provided."""
    payload = _payload_dict(peer_info, seed)
    json_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ts = int(time.time())
    flags = FLAG_HAS_SIGNATURE if seed is not None else 0
    signed = _build_signed_bytes(flags, json_bytes, ts)
    if seed is not None:
        return signed + sign(seed, signed)
    return signed


def _build_for_test(peer_info: Any, seed: bytes, *, ts: int) -> bytes:
    """Build a signed packet with an explicit timestamp (test helper)."""
    payload = _payload_dict(peer_info, seed)
    json_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signed = _build_signed_bytes(FLAG_HAS_SIGNATURE, json_bytes, ts)
    return signed + sign(seed, signed)


def parse_hello_packet(data: bytes) -> ParsedHello | None:
    """Parse a HELLO packet. Returns None for any malformed / invalid packet."""
    if len(data) < _HEADER_LEN or data[:4] != MAGIC:
        return None
    version = struct.unpack(">H", data[4:6])[0]
    if version != VERSION:
        return None  # VERSION=1 や未知バージョンは破棄
    flags = struct.unpack(">H", data[6:8])[0]
    json_len = struct.unpack(">I", data[8:12])[0]

    json_end = _HEADER_LEN + json_len
    ts_end = json_end + _TS_LEN
    if len(data) < ts_end:
        return None
    try:
        peer_dict = json.loads(data[_HEADER_LEN:json_end])
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(peer_dict, dict):
        return None

    timestamp = struct.unpack(">Q", data[json_end:ts_end])[0]
    raw_signed = data[:ts_end]

    signature: bytes | None = None
    if flags & FLAG_HAS_SIGNATURE:
        if len(data) < ts_end + _SIG_LEN:
            return None
        signature = data[ts_end:ts_end + _SIG_LEN]

    try:
        pubkey = base64.b64decode(peer_dict["pubkey"])
        x25519_pk = base64.b64decode(peer_dict["x25519_pk"])
    except (KeyError, ValueError, TypeError):
        return None
    if len(pubkey) != 32 or len(x25519_pk) != 32 or probe_x25519_low_order(x25519_pk):
        return None

    try:
        assert_peer_id_matches_pubkey(peer_dict.get("peer_id", ""), pubkey)
    except ValueError:
        return None

    try:
        X25519PublicKey.from_public_bytes(x25519_pk)
    except (ValueError, TypeError):
        return None

    return ParsedHello(
        peer_dict=peer_dict,
        pubkey=pubkey,
        x25519_pk=x25519_pk,
        timestamp=timestamp,
        signature=signature,
        raw_signed=raw_signed,
    )


def probe_x25519_low_order(x25519_pk: bytes) -> bool:
    return x25519_pk in _X25519_LOW_ORDER_POINTS


def verify_hello(parsed: ParsedHello, expected_pubkey: bytes) -> bool:
    """Verify a paired peer's HELLO (timestamp window + Ed25519 signature)."""
    if parsed.signature is None:
        return False
    now = int(time.time())
    if abs(now - parsed.timestamp) > HELLO_TIMESTAMP_TOLERANCE:
        return False
    return verify(expected_pubkey, parsed.raw_signed, parsed.signature)
