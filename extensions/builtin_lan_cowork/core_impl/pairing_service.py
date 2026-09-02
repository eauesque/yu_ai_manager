"""PairingService: state machine + DoS controls for peer pairing."""

from __future__ import annotations

import hmac
import os
import secrets
import time
import uuid
from collections import deque

from .pairing_service_limits import (
    enforce_pending_cap,
    enforce_rate_limit,
    remove_from_pending_cap,
    sync_pending_cap_after_sweep,
)
from .pairing_service_store import (
    hash_pin,
    provider_supports_cross_thread_execution,
    submit_write_with_fallback,
)

_PIN_TTL_SECONDS = 300
_PENDING_TTL_SECONDS = 600
_APPROVED_TTL_SECONDS = 300
_CLEANUP_AFTER_SECONDS = 86400
_MAX_VERIFY_ATTEMPTS = 5


class PairingService:
    _RATE_LIMIT_PER_MIN = 10
    _PENDING_CAP_PER_IP = 3

    class RateLimitExceeded(Exception):
        pass

    class PendingCapExceeded(Exception):
        pass

    def __init__(
        self,
        get_write_con,
        token_store,
        get_read_con=None,
        *,
        server_pubkey: bytes | None = None,
        server_x25519_pk: bytes | None = None,
    ) -> None:
        self._get_write_con = get_write_con
        self._get_read_con = get_read_con or get_write_con
        self._token_store = token_store
        self._server_pubkey = server_pubkey or b"\x00" * 32
        self._server_x25519_pk = server_x25519_pk
        self.threadsafe_provider = (
            provider_supports_cross_thread_execution(self._get_write_con)
            and provider_supports_cross_thread_execution(self._get_read_con)
        )
        self._ip_requests: dict[str, deque[float]] = {}
        self._ip_pending: dict[str, set[str]] = {}
        # Plain PINs are kept only in memory (not persisted to DB).
        # A server restart clears them → in-progress pairings must restart.
        # This is intentional: the hash stored in peer_pairing_requests cannot
        # be reversed, and persisting the plain PIN would weaken the security
        # model.  Fail-closed on restart is the correct trade-off.
        self._approved_pins: dict[str, str] = {}

    def request(
        self,
        *,
        peer_id: str,
        host: str,
        port: int,
        source_ip: str,
        pubkey: bytes | None = None,
        x25519_pk: bytes | None = None,
        commit_hash: bytes | None = None,
    ) -> tuple[str, str]:
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey

        from core.crypto_identity import assert_peer_id_matches_pubkey, compute_sas
        from core.crypto_identity.hello_packet import probe_x25519_low_order

        if pubkey is not None:
            assert_peer_id_matches_pubkey(peer_id, pubkey)
        if x25519_pk is not None:
            try:
                X25519PublicKey.from_public_bytes(x25519_pk)
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid x25519_pk") from exc
            if probe_x25519_low_order(x25519_pk):
                raise ValueError("low-order x25519_pk")

        self._enforce_rate_limit(source_ip)
        self._expire_prior_for_peer(peer_id)
        self._enforce_pending_cap(source_ip)
        request_id = str(uuid.uuid4())
        now = int(time.time())
        if pubkey is not None and x25519_pk is not None and self._server_x25519_pk is not None:
            sas = compute_sas(
                pubkey,
                x25519_pk,
                self._server_pubkey,
                self._server_x25519_pk,
                request_id,
            )
        elif pubkey is not None:
            # Legacy clients omit x25519_pk, so keep the old SAS input for compatibility.
            sas = compute_sas(pubkey, self._server_pubkey, request_id)
        else:
            sas = ""

        def _write() -> None:
            con = self._get_write_con()
            if pubkey is None:
                con.execute(
                    """INSERT INTO peer_pairing_requests
                       (request_id, peer_id, host, port, status, created_at, updated_at)
                       VALUES (?, ?, ?, ?, 'pending', ?, ?)""",
                    (request_id, peer_id, host, port, now, now),
                )
            else:
                con.execute(
                    """INSERT INTO peer_pairing_requests
                       (request_id, peer_id, host, port, status, created_at, updated_at,
                        pubkey, x25519_pk, commit_hash, sas, source_ip)
                       VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)""",
                    (request_id, peer_id, host, port, now, now,
                     pubkey, x25519_pk, commit_hash, sas, source_ip),
                )
            con.commit()

        submit_write_with_fallback(_write)
        self._ip_pending.setdefault(source_ip, set()).add(request_id)
        if pubkey is None:
            return request_id
        return request_id, sas

    def approve(self, request_id: str) -> str:
        row = self.get(request_id)
        if row is None or row["status"] != "pending":
            raise ValueError(f"cannot approve request in status={row and row['status']}")
        pin = f"{secrets.randbelow(100_000_000):08d}"
        now = int(time.time())
        pin_hash = hash_pin(pin)

        def _write() -> None:
            con = self._get_write_con()
            con.execute(
                """UPDATE peer_pairing_requests
                   SET pin_hash=?, pin_expires_at=?, status='approved', updated_at=?
                   WHERE request_id=?""",
                (pin_hash, now + _PIN_TTL_SECONDS, now, request_id),
            )
            con.commit()

        submit_write_with_fallback(_write)
        self._approved_pins[request_id] = pin
        if os.environ.get("YU_AI_TEST_MODE") == "1":
            if not hasattr(self, "_test_raw_pins"):
                self._test_raw_pins: dict = {}
            self._test_raw_pins[request_id] = pin
        return pin

    def reject(self, request_id: str) -> None:
        now = int(time.time())

        def _write() -> None:
            con = self._get_write_con()
            con.execute(
                """UPDATE peer_pairing_requests
                   SET status='rejected', updated_at=?, pin_hash=NULL
                   WHERE request_id=? AND status IN ('pending','approved')""",
                (now, request_id),
            )
            con.commit()

        submit_write_with_fallback(_write)
        self._remove_from_pending_cap(request_id)
        self._approved_pins.pop(request_id, None)

    def verify(
        self,
        request_id: str,
        encrypted_bundle: bytes | str,
        *,
        source_ip: str,
    ) -> tuple[bool, str | None, int | None, bytes | None]:
        row = self.get(request_id)
        if row is None or row["status"] in {"completed"} or row["status"] != "approved":
            return False, None, None, None
        if row["source_ip"] and row["source_ip"] != source_ip:
            return False, None, None, None
        now = int(time.time())
        if row["pin_expires_at"] is None or now > row["pin_expires_at"]:
            self._expire(request_id)
            return False, None, None, None

        if isinstance(encrypted_bundle, str):
            return self._verify_legacy_pin(row, request_id, encrypted_bundle)

        peer_pubkey = self._try_decrypt_bundle(
            request_id,
            row["commit_hash"],
            encrypted_bundle,
            row.get("x25519_pk"),
        )
        if peer_pubkey is None:
            attempts = row["verify_attempts"] + 1
            if attempts >= _MAX_VERIFY_ATTEMPTS:
                self._expire(request_id, final_attempts=attempts)
            else:
                self._bump_attempts(request_id, attempts)
            return False, None, None, None

        def _complete():
            con = self._get_write_con()
            raw_token, expires_at, issued_at = self._token_store.issue_into_connection(
                con, row["peer_id"], ttl_days=30, source="pairing"
            )
            con.execute(
                """UPDATE peer_pairing_requests
                   SET status='completed', pin_hash=NULL, updated_at=?
                   WHERE request_id=?""",
                (issued_at, request_id),
            )
            con.commit()
            return raw_token, expires_at

        raw_token, expires_at = submit_write_with_fallback(_complete)
        self._remove_from_pending_cap(request_id)
        self._approved_pins.pop(request_id, None)
        return True, raw_token, expires_at, peer_pubkey

    def _verify_legacy_pin(
        self,
        row: dict,
        request_id: str,
        pin: str,
    ) -> tuple[bool, str | None, int | None]:
        candidate = hash_pin(pin)
        stored = row["pin_hash"] or ""
        if not hmac.compare_digest(candidate, stored):
            attempts = row["verify_attempts"] + 1
            if attempts >= _MAX_VERIFY_ATTEMPTS:
                self._expire(request_id, final_attempts=attempts)
            else:
                self._bump_attempts(request_id, attempts)
            return False, None, None

        def _complete():
            con = self._get_write_con()
            raw_token, expires_at, issued_at = self._token_store.issue_into_connection(
                con, row["peer_id"], ttl_days=30, source="pairing"
            )
            con.execute(
                """UPDATE peer_pairing_requests
                   SET status='completed', pin_hash=NULL, updated_at=?
                   WHERE request_id=?""",
                (issued_at, request_id),
            )
            con.commit()
            return raw_token, expires_at

        raw_token, expires_at = submit_write_with_fallback(_complete)
        self._remove_from_pending_cap(request_id)
        self._approved_pins.pop(request_id, None)
        return True, raw_token, expires_at

    def get(self, request_id: str) -> dict | None:
        con = self._get_read_con()
        if self._has_pairing_crypto_columns(con):
            row = con.execute(
                """SELECT request_id, peer_id, host, port, pin_hash, pin_expires_at,
                          verify_attempts, status, created_at, updated_at,
                          pubkey, x25519_pk, commit_hash, sas, source_ip
                   FROM peer_pairing_requests WHERE request_id=?""",
                (request_id,),
            ).fetchone()
        else:
            row = con.execute(
                """SELECT request_id, peer_id, host, port, pin_hash, pin_expires_at,
                          verify_attempts, status, created_at, updated_at
                   FROM peer_pairing_requests WHERE request_id=?""",
                (request_id,),
            ).fetchone()
        if row is None:
            return None
        keys = (
            "request_id",
            "peer_id",
            "host",
            "port",
            "pin_hash",
            "pin_expires_at",
            "verify_attempts",
            "status",
            "created_at",
            "updated_at",
            "pubkey",
            "x25519_pk",
            "commit_hash",
            "sas",
            "source_ip",
        )
        data = dict(zip(keys, row, strict=False))
        data.setdefault("pubkey", None)
        data.setdefault("x25519_pk", None)
        data.setdefault("commit_hash", None)
        data.setdefault("sas", "")
        data.setdefault("source_ip", None)
        return data

    def list_pending(self) -> list:
        rows = self._get_read_con().execute(
            """SELECT request_id, peer_id, host, port, status, created_at, updated_at, sas
               FROM peer_pairing_requests WHERE status IN ('pending','approved')
               ORDER BY created_at DESC"""
        ).fetchall()
        keys = ("request_id", "peer_id", "host", "port", "status", "created_at", "updated_at", "sas")
        return [dict(zip(keys, row, strict=False)) for row in rows]

    def sweep_expired(self) -> None:
        now = int(time.time())

        def _write() -> None:
            con = self._get_write_con()
            con.execute(
                """UPDATE peer_pairing_requests
                   SET status='expired', pin_hash=NULL, updated_at=?
                   WHERE status IN ('pending','approved')
                     AND ((pin_expires_at IS NOT NULL AND ? > pin_expires_at)
                          OR (pin_expires_at IS NULL AND ? > created_at + ?))""",
                (now, now, now, _PENDING_TTL_SECONDS),
            )
            con.execute(
                """DELETE FROM peer_pairing_requests
                   WHERE status IN ('expired','rejected','completed')
                     AND updated_at < ?""",
                (now - _CLEANUP_AFTER_SECONDS,),
            )
            con.commit()

        submit_write_with_fallback(_write)
        self._sync_pending_cap_after_sweep()
        self._drop_expired_pins()

        now_f = time.time()
        for ip in list(self._ip_requests.keys()):
            dq = self._ip_requests[ip]
            while dq and now_f - dq[0] > 60:
                dq.popleft()
            if not dq:
                del self._ip_requests[ip]
        for ip in list(self._ip_pending.keys()):
            if not self._ip_pending[ip]:
                del self._ip_pending[ip]

    def _enforce_rate_limit(self, source_ip: str) -> None:
        enforce_rate_limit(self, source_ip)

    def _enforce_pending_cap(self, source_ip: str) -> None:
        enforce_pending_cap(self, source_ip)

    def _expire_prior_for_peer(self, peer_id: str) -> None:
        now = int(time.time())

        def _write() -> None:
            con = self._get_write_con()
            con.execute(
                """UPDATE peer_pairing_requests
                   SET status='expired', pin_hash=NULL, updated_at=?
                   WHERE peer_id=? AND status IN ('pending','approved')""",
                (now, peer_id),
            )
            con.commit()

        submit_write_with_fallback(_write)

    def _try_decrypt_bundle(
        self,
        request_id: str,
        commit_hash: bytes,
        encrypted_bundle: bytes,
        expected_x25519_pk: bytes | None,
    ) -> bytes | None:
        from core.crypto_identity import verify_pairing_bundle

        pin = self._approved_pins.get(request_id)
        if not pin:
            return None
        verified = verify_pairing_bundle(
            pin,
            request_id,
            bytes(commit_hash),
            encrypted_bundle,
            expected_x25519_pk=expected_x25519_pk,
        )
        if verified is None:
            return None
        peer_pubkey, bundle_x25519_pk = verified
        if expected_x25519_pk is None:
            return peer_pubkey
        # The encrypted bundle must confirm the x25519 key stored from pair/request.
        if bundle_x25519_pk is None or not hmac.compare_digest(
            bundle_x25519_pk, expected_x25519_pk
        ):
            return None
        return peer_pubkey

    def _bump_attempts(self, request_id: str, attempts: int) -> None:
        now = int(time.time())

        def _write() -> None:
            con = self._get_write_con()
            con.execute(
                "UPDATE peer_pairing_requests SET verify_attempts=?, updated_at=? WHERE request_id=?",
                (attempts, now, request_id),
            )
            con.commit()

        submit_write_with_fallback(_write)

    def _expire(self, request_id: str, final_attempts: int | None = None) -> None:
        now = int(time.time())

        def _write() -> None:
            con = self._get_write_con()
            if final_attempts is not None:
                con.execute(
                    """UPDATE peer_pairing_requests
                       SET status='expired', pin_hash=NULL, verify_attempts=?, updated_at=?
                       WHERE request_id=?""",
                    (final_attempts, now, request_id),
                )
            else:
                con.execute(
                    """UPDATE peer_pairing_requests
                       SET status='expired', pin_hash=NULL, updated_at=?
                       WHERE request_id=?""",
                    (now, request_id),
                )
            con.commit()

        submit_write_with_fallback(_write)
        self._remove_from_pending_cap(request_id)
        self._approved_pins.pop(request_id, None)

    def _drop_expired_pins(self) -> None:
        if not self._approved_pins:
            return
        rows = self._get_read_con().execute(
            """SELECT request_id FROM peer_pairing_requests
               WHERE status='approved' AND pin_expires_at IS NOT NULL AND pin_expires_at >= ?""",
            (int(time.time()),),
        ).fetchall()
        active = {row[0] for row in rows}
        for request_id in list(self._approved_pins):
            if request_id not in active:
                self._approved_pins.pop(request_id, None)

    def _remove_from_pending_cap(self, request_id: str) -> None:
        remove_from_pending_cap(self, request_id)

    def _sync_pending_cap_after_sweep(self) -> None:
        sync_pending_cap_after_sweep(self)

    @staticmethod
    def _has_pairing_crypto_columns(con) -> bool:
        cols = {row[1] for row in con.execute("PRAGMA table_info(peer_pairing_requests)")}
        return {"pubkey", "x25519_pk", "commit_hash", "sas", "source_ip"}.issubset(cols)
