"""X25519 ECDH stub for future encrypted communication (Phase 3+).

Currently only computes a shared secret. No message encryption is applied yet.
"""
from __future__ import annotations

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from .keypair import derive_x25519_seed


def compute_shared_secret(our_ed25519_seed: bytes, their_x25519_pubkey: bytes) -> bytes:
    """Compute a 32-byte X25519 ECDH shared secret.

    our_x25519_seed = derive_x25519_seed(our_ed25519_seed)
    Returns X25519(our_priv, their_pub).
    """
    our_x_seed = derive_x25519_seed(our_ed25519_seed)
    priv = X25519PrivateKey.from_private_bytes(our_x_seed)
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey

    their_pub = X25519PublicKey.from_public_bytes(their_x25519_pubkey)
    try:
        secret = priv.exchange(their_pub)
    except ValueError as exc:
        raise ValueError("invalid shared secret (all-zero)") from exc
    if secret == b"\x00" * 32:
        raise ValueError("invalid shared secret (all-zero)")
    return secret
