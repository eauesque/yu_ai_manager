"""SAS / commit-reveal / PIN-encrypted key exchange for pairing.

The pairing PIN has ~26 bits of entropy (8 digits). To make offline
brute-force of an intercepted bundle expensive, the key is derived with
scrypt (n=2^17). AES-GCM with AAD=request_id prevents bundle reuse.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

# Pairing PIN KDF: one-shot, so a higher cost than the interactive TokenStore
# (n=2^14) is acceptable. n=2^17 ≈ ~1s on a single core.
_SCRYPT_N = 131072  # 2^17
_SCRYPT_R = 8
_SCRYPT_P = 1


def _pin_kdf(pin: str, request_id: str) -> bytes:
    kdf = Scrypt(
        salt=request_id.encode("utf-8"),
        length=32,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
    )
    return kdf.derive(pin.encode("utf-8"))


def make_pairing_commit(pubkey: bytes, x25519_pk: bytes | None = None) -> tuple[bytes, bytes]:
    """Return (commit, nonce), binding x25519 when the peer supplies it."""
    nonce = secrets.token_bytes(32)
    material = pubkey + (x25519_pk or b"") + nonce
    commit = hashlib.sha256(material).digest()
    return commit, nonce


def compute_sas(
    pubkey_req: bytes,
    x25519_req: bytes | None,
    pubkey_server: bytes | str | None = None,
    x25519_server: bytes | None = None,
    request_id: str | None = None,
) -> str:
    """Return a 48-bit SAS as colon-separated uppercase HEX.

    When both peers provide x25519 keys, SAS binds Ed25519 and X25519 identity
    material. The 3-argument form is retained for legacy pairing compatibility.
    """
    if request_id is None and isinstance(pubkey_server, str):
        request_id = pubkey_server
        pubkey_server = x25519_req
        x25519_req = None
    if request_id is None or pubkey_server is None:
        raise TypeError("compute_sas requires request_id and server pubkey")
    if x25519_req is None or x25519_server is None:
        material = pubkey_req + pubkey_server + request_id.encode("utf-8")
    else:
        material = (
            pubkey_req
            + x25519_req
            + pubkey_server
            + x25519_server
            + request_id.encode("utf-8")
        )
    digest = hashlib.sha256(material).digest()
    return ":".join(f"{b:02X}" for b in digest[:6])


def encrypt_pairing_bundle(
    pin: str,
    request_id: str,
    pubkey: bytes,
    x25519_pk: bytes | None,
    nonce: bytes | None = None,
) -> bytes:
    """Encrypt pairing material under a PIN-derived key. Returns iv + ciphertext.

    New layout is pubkey(32) + x25519_pk(32) + nonce(32). If x25519_pk is
    omitted, the legacy pubkey(32) + nonce(32) layout is used.
    """
    if nonce is None:
        # Backward-compatible call shape: encrypt_pairing_bundle(pin, id, pubkey, nonce).
        nonce = x25519_pk
        x25519_pk = None
    if nonce is None:
        raise TypeError("nonce is required")
    key = _pin_kdf(pin, request_id)
    iv = os.urandom(12)
    aad = request_id.encode("utf-8")
    plain = pubkey + (x25519_pk or b"") + nonce
    ct = AESGCM(key).encrypt(iv, plain, aad)
    return iv + ct


def verify_pairing_bundle(
    pin: str,
    request_id: str,
    commit: bytes,
    encrypted_bundle: bytes,
    expected_x25519_pk: bytes | None = None,
) -> tuple[bytes, bytes | None] | None:
    """Decrypt and verify a pairing bundle. Returns (pubkey, x25519_pk)."""
    try:
        key = _pin_kdf(pin, request_id)
        iv, ct = encrypted_bundle[:12], encrypted_bundle[12:]
        aad = request_id.encode("utf-8")
        plain = AESGCM(key).decrypt(iv, ct, aad)
    except InvalidTag:
        return None
    if len(plain) == 96:
        pubkey, x25519_pk, nonce = plain[:32], plain[32:64], plain[64:96]
        expected_commit = hashlib.sha256(pubkey + x25519_pk + nonce).digest()
        if not hmac.compare_digest(expected_commit, commit):
            return None
        if expected_x25519_pk is not None and not hmac.compare_digest(
            x25519_pk, expected_x25519_pk
        ):
            return None
        return pubkey, x25519_pk
    if len(plain) != 64 or expected_x25519_pk is not None:
        return None
    pubkey, nonce = plain[:32], plain[32:64]
    if not hmac.compare_digest(hashlib.sha256(pubkey + nonce).digest(), commit):
        return None
    return pubkey, None
