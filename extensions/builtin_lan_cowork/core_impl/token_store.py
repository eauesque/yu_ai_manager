"""TokenStore: issue, verify, revoke Bearer tokens for peer auth.

Remote-side: stores scrypt(token) only, raw never persisted.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import sqlite3
import time

from core.services_core.db_write import submit_db_write

logger = logging.getLogger(__name__)

_SCRYPT_N = 16384
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_MAXMEM = 64 * 1024 * 1024
_TOKEN_BYTES = 32  # 256 bits


def _hash_token(raw: str, salt: bytes = b"yu-ai-peer-token") -> str:
    digest = hashlib.scrypt(
        raw.encode("utf-8"), salt=salt,
        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, maxmem=_SCRYPT_MAXMEM,
    )
    return digest.hex()


def _submit_write_with_fallback(fn) -> None:
    """Prefer the global single-writer, but keep injected same-thread sqlite usable.

    Tests and small local utilities may inject an in-memory sqlite connection created
    on the caller thread. Running that connection on the dedicated writer thread raises
    sqlite3.ProgrammingError, so fall back to inline execution for that case only.
    """
    try:
        return submit_db_write(fn)
    except sqlite3.ProgrammingError as exc:
        if "same thread" not in str(exc).lower():
            raise
        return fn()


def _provider_supports_cross_thread_execution(provider) -> bool:
    module = getattr(provider, "__module__", "") or ""
    name = getattr(provider, "__name__", "") or ""
    return module == "core.services_core.db_state" and name in {"get_db", "get_readonly_db"}


class TokenStore:
    def __init__(self, get_write_con, get_read_con=None) -> None:
        # Accept callables so connections are fetched at query time, not at startup.
        # Falls back to get_write_con for reads if no separate read callable is given.
        self._get_write_con = get_write_con
        self._get_read_con = get_read_con or get_write_con
        self.threadsafe_provider = (
            _provider_supports_cross_thread_execution(self._get_write_con)
            and _provider_supports_cross_thread_execution(self._get_read_con)
        )

    def issue(self, peer_id: str, ttl_days: int = 30, *, source: str = "pairing", note: str | None = None) -> tuple[str, int]:
        """Generate a fresh token, store hash, return (raw_token, expires_at)."""
        raw, now, expires_at, token_hash = self._build_issue_values(peer_id, ttl_days)

        def _write() -> None:
            con = self._get_write_con()
            self._upsert_issued_token(
                con,
                peer_id,
                token_hash=token_hash,
                issued_at=now,
                expires_at=expires_at,
                source=source,
                note=note,
            )
            con.commit()

        _submit_write_with_fallback(_write)
        return raw, expires_at

    def issue_into_connection(
        self,
        con,
        peer_id: str,
        ttl_days: int = 30,
        *,
        source: str = "pairing",
        note: str | None = None,
    ) -> tuple[str, int, int]:
        """Generate and persist a token using the caller-managed transaction."""
        raw, now, expires_at, token_hash = self._build_issue_values(peer_id, ttl_days)
        self._upsert_issued_token(
            con,
            peer_id,
            token_hash=token_hash,
            issued_at=now,
            expires_at=expires_at,
            source=source,
            note=note,
        )
        return raw, expires_at, now

    def has_token(self, peer_id: str) -> bool:
        """Return True if any active (non-revoked) token exists for peer_id.

        Does not check expiry — used to distinguish "never paired" (no row)
        from "paired but token expired/lost" (row present).
        """
        if not peer_id:
            return False
        row = self._get_read_con().execute(
            "SELECT 1 FROM peer_tokens WHERE peer_id=? AND revoked_at IS NULL",
            (peer_id,),
        ).fetchone()
        return row is not None

    def verify(self, peer_id: str, raw: str) -> bool:
        """Constant-time check against stored hash, TTL, and revocation."""
        if not peer_id or not raw:
            return False
        row = self._get_read_con().execute(
            "SELECT token_hash, expires_at, revoked_at FROM peer_tokens WHERE peer_id=?",
            (peer_id,),
        ).fetchone()
        if row is None:
            return False
        stored_hash, expires_at, revoked_at = row[0], row[1], row[2]
        if revoked_at is not None:
            return False
        if int(time.time()) > expires_at:
            return False
        candidate = _hash_token(raw)
        return hmac.compare_digest(candidate, stored_hash)

    def revoke(self, peer_id: str) -> None:
        def _write() -> None:
            con = self._get_write_con()
            con.execute(
                "UPDATE peer_tokens SET revoked_at=? WHERE peer_id=? AND revoked_at IS NULL",
                (int(time.time()), peer_id),
            )
            con.commit()

        _submit_write_with_fallback(_write)

    def renew_if_not_revoked(self, peer_id: str, ttl_days: int = 30) -> tuple[bool, str | None, int | None]:
        """Atomically issue a fresh token only if the peer is not revoked."""
        if not peer_id:
            return False, None, None

        def _write():
            con = self._get_write_con()
            try:
                con.execute("BEGIN IMMEDIATE")
                row = con.execute(
                    "SELECT revoked_at FROM peer_tokens WHERE peer_id=?",
                    (peer_id,),
                ).fetchone()
                if row is not None and row[0] is not None:
                    con.rollback()
                    return False, None, None
                raw, expires_at, _issued_at = self.issue_into_connection(
                    con,
                    peer_id,
                    ttl_days=ttl_days,
                    source="renew",
                )
                con.commit()
                return True, raw, expires_at
            except Exception:
                con.rollback()
                raise

        return _submit_write_with_fallback(_write)

    @staticmethod
    def _build_issue_values(peer_id: str, ttl_days: int) -> tuple[str, int, int, str]:
        raw = secrets.token_urlsafe(_TOKEN_BYTES)
        now = int(time.time())
        expires_at = now + ttl_days * 86400
        token_hash = _hash_token(raw)
        return raw, now, expires_at, token_hash

    @staticmethod
    def _upsert_issued_token(
        con,
        peer_id: str,
        *,
        token_hash: str,
        issued_at: int,
        expires_at: int,
        source: str,
        note: str | None,
    ) -> None:
        con.execute(
            """INSERT INTO peer_tokens
               (peer_id, token_hash, issued_at, expires_at, revoked_at, source, note)
               VALUES (?, ?, ?, ?, NULL, ?, ?)
               ON CONFLICT(peer_id) DO UPDATE SET
                 token_hash=excluded.token_hash,
                 issued_at=excluded.issued_at,
                 expires_at=excluded.expires_at,
                 revoked_at=NULL,
                 source=excluded.source,
                 note=excluded.note""",
            (peer_id, token_hash, issued_at, expires_at, source, note),
        )

    def list_active(self) -> list[dict]:
        now = int(time.time())
        rows = self._get_read_con().execute(
            """SELECT peer_id, issued_at, expires_at, source, note
               FROM peer_tokens
               WHERE revoked_at IS NULL AND expires_at > ?
               ORDER BY issued_at DESC""",
            (now,),
        ).fetchall()
        return [
            {"peer_id": r[0], "issued_at": r[1], "expires_at": r[2],
             "source": r[3], "note": r[4]}
            for r in rows
        ]
