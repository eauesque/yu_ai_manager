#!/usr/bin/env python3
"""Generate byte-compat test vectors for the Rust pairing crypto port (Increment E1).

Imports the REAL Python pairing crypto so the Rust implementation can be pinned
to it exactly. Covers the divergence risks the design flagged (MF-E1..E5):

- three distinct scrypt uses whose OUTPUT LENGTHS differ (the inventory got this
  wrong twice): token hash 64B, PIN hash 64B, PIN->AES key 32B
- HKDF-SHA256 X25519 seed derivation (salt empty, info versioned)
- commit / SAS in both the 96B (x25519-bound) and 64B (legacy) shapes
- AES-GCM under a fixed IV so ciphertext+tag can be asserted byte-for-byte
  (AES-GCM is fully deterministic given key/iv/aad/plaintext, so this is
  strictly stronger than only checking that decryption round-trips)
- the X25519 low-order deny-list, emitted mechanically from the Python constant
  so the Rust copy is forced to stay in sync

Separate from peer_transport_vectors.json: the PIN KDF is n=2^17 (~128 MiB,
~1s), so this generator is deliberately not run alongside the cheap ones.

Run:  uv run python scripts/gen_peer_pairing_vectors.py
Output: tests/vectors/peer_pairing_vectors.json
"""
from __future__ import annotations

import base64
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sys

from lan_cowork_repo import vectors_dir  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.crypto_identity.hello_packet import _X25519_LOW_ORDER_POINTS
from core.crypto_identity.keypair import (
    derive_x25519_seed,
    ed25519_pubkey_bytes,
    x25519_pubkey_bytes,
)
from core.crypto_identity.pairing import (
    _pin_kdf,
    compute_sas,
    encrypt_pairing_bundle,
)
from extensions.builtin_lan_cowork.core_impl.pairing_service_store import hash_pin
from extensions.builtin_lan_cowork.core_impl.token_store import _hash_token

# Deterministic inputs so every field below is reproducible.
CLIENT_SEED = bytes(range(1, 33))
SERVER_SEED = bytes(range(101, 133))
REQUEST_ID = "11111111-2222-3333-4444-555555555555"
PIN = "12345678"
FIXED_IV = bytes.fromhex("000102030405060708090a0b")
PAIR_NONCE = bytes(range(64, 96))  # the 32-byte commit nonce


def scrypt_vectors() -> dict:
    """The three scrypt uses. Output lengths intentionally differ — pin each."""
    token_hash = _hash_token("peer-token-vector-001")
    pin_hash = hash_pin(PIN)
    pin_key = _pin_kdf(PIN, REQUEST_ID)
    return {
        "token_hash": {
            "note": "token_store._hash_token: n=2^14, salt='yu-ai-peer-token', dklen unset -> 64 bytes",
            "raw": "peer-token-vector-001",
            "hex": token_hash,
            "hex_len": len(token_hash),
        },
        "pin_hash": {
            "note": "pairing_service_store.hash_pin: n=2^14, salt='yu-ai-pairing-pin', dklen unset -> 64 bytes",
            "pin": PIN,
            "hex": pin_hash,
            "hex_len": len(pin_hash),
        },
        "pin_kdf": {
            "note": "pairing._pin_kdf: n=2^17, salt=request_id (NOT a constant), length=32 explicit",
            "pin": PIN,
            "request_id": REQUEST_ID,
            "key_hex": pin_key.hex(),
            "key_len_bytes": len(pin_key),
        },
    }


def identity_vectors() -> dict:
    return {
        "client": {
            "ed25519_seed_hex": CLIENT_SEED.hex(),
            "ed25519_pubkey_hex": ed25519_pubkey_bytes(CLIENT_SEED).hex(),
            "x25519_seed_hex": derive_x25519_seed(CLIENT_SEED).hex(),
            "x25519_pubkey_hex": x25519_pubkey_bytes(CLIENT_SEED).hex(),
        },
        "server": {
            "ed25519_seed_hex": SERVER_SEED.hex(),
            "ed25519_pubkey_hex": ed25519_pubkey_bytes(SERVER_SEED).hex(),
            "x25519_pubkey_hex": x25519_pubkey_bytes(SERVER_SEED).hex(),
        },
        "hkdf_info_utf8": "yu-ai-lan-cowork-x25519-v1",
    }


def commit_vectors() -> dict:
    """commit = sha256(pubkey ‖ x25519_pk ‖ nonce) (96B) or sha256(pubkey ‖ nonce) (64B)."""
    pub = ed25519_pubkey_bytes(CLIENT_SEED)
    x = x25519_pubkey_bytes(CLIENT_SEED)
    return {
        "nonce_hex": PAIR_NONCE.hex(),
        "v2": {
            "material": "pubkey||x25519_pk||nonce",
            "commit_hex": hashlib.sha256(pub + x + PAIR_NONCE).hexdigest(),
        },
        "legacy": {
            "material": "pubkey||nonce",
            "commit_hex": hashlib.sha256(pub + PAIR_NONCE).hexdigest(),
        },
    }


def sas_vectors() -> dict:
    """SAS = first 6 bytes of sha256(material), uppercase hex, colon separated."""
    cpub = ed25519_pubkey_bytes(CLIENT_SEED)
    cx = x25519_pubkey_bytes(CLIENT_SEED)
    spub = ed25519_pubkey_bytes(SERVER_SEED)
    sx = x25519_pubkey_bytes(SERVER_SEED)
    return {
        "v2": {
            "material": "pubkey_req||x25519_req||pubkey_server||x25519_server||request_id",
            "sas": compute_sas(cpub, cx, spub, sx, REQUEST_ID),
        },
        "legacy": {
            "material": "pubkey_req||pubkey_server||request_id",
            # 3-argument legacy shape goes through the positional shim.
            "sas": compute_sas(cpub, None, spub, None, REQUEST_ID),
        },
        "request_id": REQUEST_ID,
    }


def aead_vectors() -> dict:
    """AES-256-GCM. Fixed IV -> ciphertext+tag are deterministic and assertable.

    Wire layout produced by encrypt_pairing_bundle is iv(12) || ct || tag(16);
    Python's AESGCM appends the tag to the ciphertext, whereas openssl takes the
    tag as a separate argument — the most likely source of a byte bug (MF-E3).
    """
    key = _pin_kdf(PIN, REQUEST_ID)
    aad = REQUEST_ID.encode("utf-8")
    pub = ed25519_pubkey_bytes(CLIENT_SEED)
    x = x25519_pubkey_bytes(CLIENT_SEED)

    plain_v2 = pub + x + PAIR_NONCE  # 96B
    plain_legacy = pub + PAIR_NONCE  # 64B
    ct_v2 = AESGCM(key).encrypt(FIXED_IV, plain_v2, aad)
    ct_legacy = AESGCM(key).encrypt(FIXED_IV, plain_legacy, aad)

    # One real bundle (random IV inside) to exercise the decrypt direction.
    real_bundle = encrypt_pairing_bundle(PIN, REQUEST_ID, pub, x, PAIR_NONCE)

    return {
        "key_hex": key.hex(),
        "iv_hex": FIXED_IV.hex(),
        "aad_utf8": REQUEST_ID,
        "tag_len_bytes": 16,
        "v2": {
            "plaintext_len": len(plain_v2),
            "plaintext_hex": plain_v2.hex(),
            "ct_and_tag_hex": ct_v2.hex(),
            "wire_hex": (FIXED_IV + ct_v2).hex(),
        },
        "legacy": {
            "plaintext_len": len(plain_legacy),
            "plaintext_hex": plain_legacy.hex(),
            "ct_and_tag_hex": ct_legacy.hex(),
            "wire_hex": (FIXED_IV + ct_legacy).hex(),
        },
        "real_bundle_b64": base64.b64encode(real_bundle).decode("ascii"),
        "negative": {
            "wrong_aad_utf8": "99999999-8888-7777-6666-555555555555",
            "short_bundle_hex": (FIXED_IV + b"\x00" * 8).hex(),  # < 28 bytes total
        },
    }


def deny_list_vector() -> dict:
    """Emit the Python deny-list mechanically so Rust is forced to match (MF-E5)."""
    points = sorted(p.hex() for p in _X25519_LOW_ORDER_POINTS)
    return {
        "note": "Generated from core.crypto_identity.hello_packet._X25519_LOW_ORDER_POINTS. "
        "Rust must assert set equality against this.",
        "count": len(points),
        "all_32_bytes": all(len(p) == 64 for p in points),
        "points_hex": points,
    }


def main() -> None:
    vectors = {
        "_note": "Generated by scripts/gen_peer_pairing_vectors.py from the real Python "
        "pairing crypto. Do not edit by hand. Rust peer_pairing_crypto tests assert "
        "byte-equality against these (design 2026-07-19 Increment E1, MF-E1..E5).",
        "scrypt": scrypt_vectors(),
        "identity": identity_vectors(),
        "commit": commit_vectors(),
        "sas": sas_vectors(),
        "aead": aead_vectors(),
        "x25519_low_order_deny_list": deny_list_vector(),
    }
    out = vectors_dir() / "peer_pairing_vectors.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(vectors, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    s = vectors["scrypt"]
    print(f"  token_hash : {s['token_hash']['hex_len']} hex")
    print(f"  pin_hash   : {s['pin_hash']['hex_len']} hex")
    print(f"  pin_kdf key: {s['pin_kdf']['key_len_bytes']} bytes")
    print(f"  deny-list  : {vectors['x25519_low_order_deny_list']['count']} points, "
          f"all 32B={vectors['x25519_low_order_deny_list']['all_32_bytes']}")
    print(f"  SAS v2     : {vectors['sas']['v2']['sas']}")


if __name__ == "__main__":
    main()
