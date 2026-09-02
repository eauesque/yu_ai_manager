"""In-memory token store for LAN collection sharing.

Tokens are ephemeral (15-minute TTL, memory-only) and scoped to a
snapshot of allowed file IDs at creation time.
"""

import logging
import secrets
import threading
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_TTL_SECONDS = 900  # 15 minutes
_SWEEP_INTERVAL = 300  # 5 minutes

_lock = threading.Lock()
_tokens: dict[str, "ShareToken"] = {}
_last_sweep: float = 0.0


@dataclass(frozen=True, slots=True)
class ShareToken:
    """Immutable snapshot of a shared collection."""

    token: str
    collection_id: int
    collection_name: str
    allowed_file_ids: frozenset[int]
    created_at: float
    expires_at: float


def create_share_token(collection_id: int) -> ShareToken:
    """Create a share token for a collection.

    Snapshots the current favorite file IDs so that the guest can only
    access files that existed at token-creation time.
    """
    from core.services_core.db_state import get_db

    con = get_db()
    row = con.execute("SELECT name FROM collections WHERE id=?", (collection_id,)).fetchone()
    name = row[0] if row else None
    if not name:
        raise ValueError(f"Collection {collection_id} not found")

    file_pairs = con.execute(
        "SELECT f.id, f.path FROM favorites fav "
        "JOIN files f ON f.id=fav.file_id AND f.is_deleted=0 "
        "WHERE fav.collection_id=? ORDER BY fav.added_at DESC",
        (collection_id,),
    )
    file_pairs = [(row[0], row[1]) for row in file_pairs]
    if not file_pairs:
        raise ValueError(f"Collection {collection_id} has no files")

    file_ids = frozenset(fid for fid, _path in file_pairs)
    now = time.time()
    token = secrets.token_urlsafe(12)

    share = ShareToken(
        token=token,
        collection_id=collection_id,
        collection_name=name,
        allowed_file_ids=file_ids,
        created_at=now,
        expires_at=now + _TTL_SECONDS,
    )

    with _lock:
        _tokens[token] = share
        _maybe_sweep()

    logger.info(
        "LAN share created: token=%s collection=%d (%s) files=%d",
        token[:6] + "...",
        collection_id,
        name,
        len(file_ids),
    )
    return share


def validate_token(token: str) -> ShareToken | None:
    """Return the ShareToken if valid and not expired, else None.

    Performs lazy deletion of expired tokens.
    """
    with _lock:
        share = _tokens.get(token)
        if share is None:
            return None
        if time.time() > share.expires_at:
            del _tokens[token]
            return None
        _maybe_sweep()
        return share


def revoke_token(token: str) -> bool:
    """Revoke (delete) a token. Returns True if it existed."""
    with _lock:
        return _tokens.pop(token, None) is not None


def cleanup_expired() -> int:
    """Remove all expired tokens. Returns count removed."""
    now = time.time()
    with _lock:
        expired = [k for k, v in _tokens.items() if now > v.expires_at]
        for k in expired:
            del _tokens[k]
    if expired:
        logger.debug("LAN share cleanup: removed %d expired tokens", len(expired))
    return len(expired)


def _maybe_sweep() -> None:
    """Run cleanup if sweep interval has elapsed. Caller must hold _lock."""
    global _last_sweep
    now = time.time()
    if now - _last_sweep < _SWEEP_INTERVAL:
        return
    _last_sweep = now
    expired = [k for k, v in _tokens.items() if now > v.expires_at]
    for k in expired:
        del _tokens[k]
