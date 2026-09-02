"""Ed25519 / X25519 key operations for LAN Cowork crypto identity.

This module depends ONLY on the cryptography library (no project imports)
to avoid circular dependencies.
"""
from __future__ import annotations

import os

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

# Domain separation tag for X25519 seed derivation. Versioned so a future
# change of derivation parameters is explicit and detectable.
_X25519_HKDF_INFO = b"yu-ai-lan-cowork-x25519-v1"


def generate_ed25519_seed() -> bytes:
    """Generate 32 bytes of cryptographic random seed (the private key)."""
    return os.urandom(32)


def ed25519_privkey(seed: bytes) -> Ed25519PrivateKey:
    """Restore an Ed25519PrivateKey from a 32-byte raw seed."""
    return Ed25519PrivateKey.from_private_bytes(seed)


def ed25519_pubkey_bytes(seed: bytes) -> bytes:
    """Derive the Ed25519 public key bytes (32B) from a seed."""
    pub = ed25519_privkey(seed).public_key()
    return pub.public_bytes(Encoding.Raw, PublicFormat.Raw)


def derive_x25519_seed(ed25519_seed: bytes) -> bytes:
    """Derive an independent X25519 seed from an Ed25519 seed via HKDF-SHA256.

    Reusing the Ed25519 seed directly for X25519 would be cross-protocol key
    reuse (violates RFC 8032 / NIST SP 800-186 key separation). HKDF gives an
    independent 32-byte seed. salt is empty because the Ed25519 seed already
    carries full entropy.
    """
    hkdf = HKDF(algorithm=SHA256(), length=32, salt=b"", info=_X25519_HKDF_INFO)
    return hkdf.derive(ed25519_seed)


def x25519_pubkey_bytes(ed25519_seed: bytes) -> bytes:
    """Derive the X25519 public key bytes (32B) from an Ed25519 seed."""
    x_seed = derive_x25519_seed(ed25519_seed)
    pub = X25519PrivateKey.from_private_bytes(x_seed).public_key()
    return pub.public_bytes(Encoding.Raw, PublicFormat.Raw)


def sign(seed: bytes, message: bytes) -> bytes:
    """Return a 64-byte Ed25519 signature over message.

    The message is signed as raw bytes — Ed25519 internally hashes with
    SHA-512, so pre-hashing is unnecessary and incorrect.
    """
    return ed25519_privkey(seed).sign(message)


def verify(pubkey: bytes, message: bytes, sig: bytes) -> bool:
    """Verify an Ed25519 signature. Returns False on any failure (never raises)."""
    try:
        Ed25519PublicKey.from_public_bytes(pubkey).verify(sig, message)
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False
