"""Client-side request signing.

Canonical message:
  METHOD.upper() + "\n"
  + full_path    + "\n"   (Blueprint prefix included)
  + query_string + "\n"
  + ts_str       + "\n"
  + body_hash    + "\n"   (sha256(raw_body).hexdigest())
"""
from __future__ import annotations

import base64
import hashlib
import time
import uuid

from .keypair import sign

# Endpoints that change state and therefore require a nonce (non-idempotent).
# Suffix match against the full path.
NONCE_REQUIRED_SUFFIXES = (
    "/api/peer/message",
    "/api/peer/token/renew",
    "/api/peer/generate",
    "/api/peer/cancel",
    "/api/peer/sync/push",
    "/api/peer/sync/notify",
    "/api/peer/negotiate",
)
# Prefix match (import/* and fleet/*).
NONCE_REQUIRED_PREFIXES = (
    "/api/peer/infer/",
    "/api/peer/import/",
    "/ext/lan_cowork/fleet/",
)


def build_canonical_message(
    method: str, path: str, query_string: str, ts_str: str, body: bytes
) -> bytes:
    body_hash = hashlib.sha256(body or b"").hexdigest()
    parts = [
        method.upper(),
        path,
        query_string or "",
        ts_str,
        body_hash,
    ]
    return ("\n".join(parts) + "\n").encode("utf-8")


def make_signature_headers(
    seed: bytes, method: str, path: str, query_string: str, body: bytes
) -> dict[str, str]:
    ts_str = str(int(time.time()))
    canonical = build_canonical_message(method, path, query_string, ts_str, body)
    sig = sign(seed, canonical)
    return {
        "X-Peer-Ts": ts_str,
        "X-Peer-Sig": base64.urlsafe_b64encode(sig).decode("ascii"),
    }


def make_nonce_header() -> dict[str, str]:
    return {"X-Peer-Nonce": str(uuid.uuid4())}


def path_requires_nonce(path: str) -> bool:
    if any(path.endswith(s) for s in NONCE_REQUIRED_SUFFIXES):
        return True
    return any(path.startswith(p) for p in NONCE_REQUIRED_PREFIXES)
