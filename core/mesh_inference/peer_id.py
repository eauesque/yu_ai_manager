"""peer_id format validator shared by state, persistence, and API layers.

Accepts alphanumeric + [_-.:] up to 64 chars. Rejects empty, None, paths,
control characters, and oversized inputs. One place so future tightening
touches a single file.
"""
from __future__ import annotations

import re

_PEER_ID_RE = re.compile(r"^[A-Za-z0-9_\-.:]{1,64}$")


def is_valid_peer_id(peer_id: object) -> bool:
    """Return True if *peer_id* is a safe overlay key.

    `.` and `:` are allowed because existing conventions include values like
    `mdns-abc12345` and `host.local:8080`.
    """
    if not isinstance(peer_id, str):
        return False
    return bool(_PEER_ID_RE.match(peer_id))
