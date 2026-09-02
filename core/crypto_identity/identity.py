"""peer_id derivation and fingerprint utilities.

peer_id is the hex of the first 16 bytes of sha256(ed25519_pubkey). This binds
the node identity cryptographically to its public key.
"""
from __future__ import annotations

import hashlib


def derive_peer_id(ed25519_pubkey: bytes) -> str:
    """Return sha256(pubkey)[:16].hex() — 16 bytes as 32 hex characters."""
    return hashlib.sha256(ed25519_pubkey).digest()[:16].hex()


def fingerprint_display(ed25519_pubkey: bytes) -> str:
    """Return the first 6 bytes of sha256(pubkey) as colon-separated uppercase HEX.

    Example: "E3:F7:2A:91:B5:D2". Used for SAS / UI display. 48 bits is enough
    for a human to visually compare two screens.
    """
    digest = hashlib.sha256(ed25519_pubkey).digest()
    return ":".join(f"{b:02X}" for b in digest[:6])


def assert_peer_id_matches_pubkey(peer_id: str, pubkey: bytes) -> None:
    """Raise ValueError if derive_peer_id(pubkey) != peer_id.

    Must be called at every external input point:
      1. hello_packet.parse_hello_packet()
      2. POST /api/peer/register
      3. POST /api/peer/pair/request
      4. POST /api/peer/pair/verify (after bundle decryption reveals pubkey)
      5. PeerRegistry.upsert() (final guard before registry write)
    """
    expected = derive_peer_id(pubkey)
    if expected != peer_id:
        raise ValueError(
            f"peer_id mismatch: expected {expected!r}, got {peer_id!r}"
        )
