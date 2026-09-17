"""core.crypto_identity — shared cryptographic identity for LAN networking.

Other modules import ONLY from this package root.
"""
from __future__ import annotations

from .future_encryption import compute_shared_secret
from .hello_packet import (
    HELLO_TIMESTAMP_TOLERANCE,
    ParsedHello,
    build_hello_packet,
    parse_hello_packet,
    verify_hello,
)
from .identity import (
    assert_peer_id_matches_pubkey,
    derive_peer_id,
    fingerprint_display,
)
from .keypair import (
    derive_x25519_seed,
    ed25519_privkey,
    ed25519_pubkey_bytes,
    generate_ed25519_seed,
    sign,
    verify,
    x25519_pubkey_bytes,
)
from .pairing import (
    compute_sas,
    encrypt_pairing_bundle,
    make_pairing_commit,
    verify_pairing_bundle,
)
from .request_signer import (
    build_canonical_message,
    make_nonce_header,
    make_signature_headers,
    path_requires_nonce,
)
from .request_verifier import (
    REQUEST_TIMESTAMP_TOLERANCE,
    NonceResult,
    NonceStore,
    require_peer_signature,
    verify_request_signature,
)

__all__ = [
    "HELLO_TIMESTAMP_TOLERANCE",
    "NonceResult",
    "NonceStore",
    "ParsedHello",
    "REQUEST_TIMESTAMP_TOLERANCE",
    "assert_peer_id_matches_pubkey",
    "build_canonical_message",
    "build_hello_packet",
    "compute_sas",
    "compute_shared_secret",
    "derive_peer_id",
    "derive_x25519_seed",
    "ed25519_privkey",
    "ed25519_pubkey_bytes",
    "encrypt_pairing_bundle",
    "fingerprint_display",
    "generate_ed25519_seed",
    "make_nonce_header",
    "make_pairing_commit",
    "make_signature_headers",
    "parse_hello_packet",
    "path_requires_nonce",
    "require_peer_signature",
    "sign",
    "verify",
    "verify_hello",
    "verify_pairing_bundle",
    "verify_request_signature",
    "x25519_pubkey_bytes",
]
