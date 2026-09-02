"""Write helpers for LAN Cowork peer registry persistence."""

from __future__ import annotations

import json
import threading

from extensions.builtin_lan_cowork.core_impl.models import PeerInfo

_PEER_UPDATE_FLUSH_DELAY_SEC = 0.5
_PEER_UPDATE_FLUSH_THRESHOLD = 64
_peer_update_lock = threading.Lock()
_peer_update_timer: threading.Timer | None = None
_pending_attempted: dict[str, int] = {}
_pending_reached: dict[str, int] = {}


def delete_peer_record(peer_id: str) -> None:
    from core.services_core.db_write import submit_db_write

    def _write() -> None:
        from core.services_core.db_state import get_db

        con = get_db()
        con.execute("DELETE FROM peers WHERE peer_id=?", (peer_id,))
        con.commit()

    submit_db_write(_write)


def cleanup_local_peer_record(peer_id: str) -> None:
    """Best-effort removal of the local-self row from the peers table.

    Called from ``PeerRegistry._load_all`` during startup. Uses
    ``submit_db_write_no_wait`` so the caller does not pay the writer
    cold-start cost (otherwise the startup load would still block on the
    first writer transaction even after :func:`prune_stale_peers` was made
    asynchronous).
    """
    from core.services_core.db_write import submit_db_write_no_wait

    def _write() -> None:
        from core.services_core.db_state import get_db

        con = get_db()
        con.execute("DELETE FROM peers WHERE peer_id=?", (peer_id,))
        con.commit()

    submit_db_write_no_wait(_write)


def update_peer_reached(peer_id: str, ts: int) -> None:
    """Mark peer as successfully reached at ``ts`` (UNIX seconds).

    Updates both ``last_reached_at`` and ``last_attempted_at`` since a
    successful fetch is also an attempt.
    """
    _queue_peer_update(peer_id, ts, reached=True)


def update_peer_attempted(peer_id: str, ts: int) -> None:
    """Mark a fetch attempt at ``ts`` (UNIX seconds) without claiming success."""
    _queue_peer_update(peer_id, ts, reached=False)


def _queue_peer_update(peer_id: str, ts: int, *, reached: bool) -> None:
    global _peer_update_timer
    flush_now = False
    with _peer_update_lock:
        if reached:
            _pending_reached[peer_id] = max(ts, _pending_reached.get(peer_id, 0))
            _pending_attempted[peer_id] = max(ts, _pending_attempted.get(peer_id, 0))
        else:
            _pending_attempted[peer_id] = max(ts, _pending_attempted.get(peer_id, 0))
        pending_count = len(_pending_attempted) + len(_pending_reached)
        if pending_count >= _PEER_UPDATE_FLUSH_THRESHOLD:
            flush_now = True
            if _peer_update_timer is not None:
                _peer_update_timer.cancel()
                _peer_update_timer = None
        elif _peer_update_timer is None:
            _peer_update_timer = threading.Timer(_PEER_UPDATE_FLUSH_DELAY_SEC, _flush_pending_peer_updates)
            _peer_update_timer.daemon = True
            _peer_update_timer.start()
    if flush_now:
        _flush_pending_peer_updates()


def _flush_pending_peer_updates() -> None:
    global _peer_update_timer
    with _peer_update_lock:
        attempted = dict(_pending_attempted)
        reached = dict(_pending_reached)
        _pending_attempted.clear()
        _pending_reached.clear()
        _peer_update_timer = None
    if not attempted and not reached:
        return

    from core.services_core.db_write import submit_db_write_no_wait

    def _write() -> None:
        from core.services_core.db_state import get_db

        con = get_db()
        if reached:
            con.executemany(
                """UPDATE peers
                      SET last_reached_at=?, last_attempted_at=?, updated_at=?
                    WHERE peer_id=?""",
                [(ts, ts, ts, peer_id) for peer_id, ts in reached.items()],
            )
        attempted_rows = [
            (ts, ts, peer_id)
            for peer_id, ts in attempted.items()
            if ts > reached.get(peer_id, -1)
        ]
        if attempted_rows:
            con.executemany(
                "UPDATE peers SET last_attempted_at=?, updated_at=? WHERE peer_id=?",
                attempted_rows,
            )
        con.commit()

    submit_db_write_no_wait(_write)


def flush_peer_registry_updates_for_tests() -> None:
    """Flush queued peer telemetry writes synchronously in tests."""
    with _peer_update_lock:
        timer = _peer_update_timer
    if timer is not None:
        timer.cancel()
    _flush_pending_peer_updates()


def prune_stale_peers(cutoff_ts: int) -> list[str]:
    """Delete peer rows whose last_reached_at is older than ``cutoff_ts``.

    Rows that have NEVER been reached (last_reached_at IS NULL) are kept
    if they are newer than the cutoff (created_at >= cutoff_ts) so freshly
    paired peers that haven't yet polled don't get nuked. Older
    never-reached rows are pruned too.

    Returns the list of deleted peer_ids (best-effort — the actual DELETE
    is dispatched fire-and-forget so the caller does not pay the cost of
    the first writer-thread cold-start during LAN Cowork registry load).
    The caller already filters ``stale_ids`` out of its in-memory view
    when reloading peers, so eventual consistency on the DB side is fine.
    """
    from core.services_core.db_state import get_readonly_db
    from core.services_core.db_write import submit_db_write_no_wait

    con = get_readonly_db()
    rows = con.execute(
        """SELECT peer_id FROM peers
            WHERE (last_reached_at IS NOT NULL AND last_reached_at < ?)
               OR (last_reached_at IS NULL AND created_at < ?)""",
        (cutoff_ts, cutoff_ts),
    )
    stale_ids = [r[0] for r in rows]
    if not stale_ids:
        return []

    def _write() -> None:
        from core.services_core.db_state import get_db

        wcon = get_db()
        # Re-apply the stale predicate at DELETE time so an in-flight
        # heartbeat that updates ``last_reached_at`` between the SELECT
        # above and this DELETE doesn't get its peer row erased. Belt-and-
        # suspenders for the fire-and-forget path (low probability in
        # practice — startup runs before discovery kicks in — but cheap).
        wcon.executemany(
            "DELETE FROM peers WHERE peer_id=? AND ("
            "  (last_reached_at IS NOT NULL AND last_reached_at < ?)"
            "  OR (last_reached_at IS NULL AND created_at < ?)"
            ")",
            [(pid, cutoff_ts, cutoff_ts) for pid in stale_ids],
        )
        wcon.commit()

    submit_db_write_no_wait(_write)
    return stale_ids


def _select_unpaired_unreached_peer_ids(con, cutoff_ts: int) -> list[str]:
    rows = con.execute(
        """SELECT peer_id FROM peers
            WHERE (token IS NULL OR token = '')
              AND last_reached_at IS NULL
              AND created_at < ?""",
        (cutoff_ts,),
    )
    return [r[0] for r in rows]


def _delete_unpaired_unreached_peer_ids(con, peer_ids: list[str], cutoff_ts: int) -> None:
    con.executemany(
        "DELETE FROM peers WHERE peer_id=?"
        " AND (token IS NULL OR token = '')"
        " AND last_reached_at IS NULL"
        " AND created_at < ?",
        [(pid, cutoff_ts) for pid in peer_ids],
    )


def _select_and_delete_unpaired_unreached(con, cutoff_ts: int) -> list[str]:
    peer_ids = _select_unpaired_unreached_peer_ids(con, cutoff_ts)
    if not peer_ids:
        return []
    _delete_unpaired_unreached_peer_ids(con, peer_ids, cutoff_ts)
    con.commit()
    return peer_ids


def prune_unpaired_unreached_peers(cutoff_ts: int) -> list[str]:
    """Delete discovery rows that never became real peers.

    Targets rows that are (a) NOT paired (token IS NULL or empty) AND
    (b) never successfully reached (last_reached_at IS NULL) AND
    (c) older than ``cutoff_ts`` (created_at < cutoff_ts). These are dead
    discovery artifacts (e.g. a peer that restarted with a new ephemeral
    identity/port and was announced but never paired or contacted). Paired
    peers (any token) and freshly-created rows are always preserved, so this
    is safe to run on every registry load with a short (1h) cutoff.

    Returns deleted peer_ids (best-effort; DELETE is dispatched fire-and-forget).
    """
    from core.services_core.db_state import get_readonly_db
    from core.services_core.db_write import submit_db_write_no_wait

    con = get_readonly_db()
    unpaired_ids = _select_unpaired_unreached_peer_ids(con, cutoff_ts)
    if not unpaired_ids:
        return []

    def _write() -> None:
        from core.services_core.db_state import get_db

        wcon = get_db()
        # Re-apply the unpaired/unreached predicate at DELETE time so an
        # in-flight pairing or heartbeat between the SELECT above and this
        # DELETE doesn't get its peer row erased. Belt-and-suspenders for
        # the fire-and-forget path, matching prune_stale_peers.
        _delete_unpaired_unreached_peer_ids(wcon, unpaired_ids, cutoff_ts)
        wcon.commit()

    submit_db_write_no_wait(_write)
    return unpaired_ids


def upsert_peer_record(peer: PeerInfo) -> None:
    import time as _time

    from core.services_core.db_write import submit_db_write

    def _write() -> None:
        from core.services_core.db_state import get_db

        con = get_db()
        now = int(_time.time())
        con.execute(
            """INSERT INTO peers (peer_id, name, api_host, api_port,
                                  token, token_expires_at, token_issued_at,
                                  pubkey, x25519_pk, inference_types,
                                  created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(peer_id) DO UPDATE SET
                 name=excluded.name, api_host=excluded.api_host, api_port=excluded.api_port,
                 token=excluded.token, token_expires_at=excluded.token_expires_at,
                 token_issued_at=excluded.token_issued_at,
                 pubkey=COALESCE(excluded.pubkey, pubkey),
                 x25519_pk=COALESCE(excluded.x25519_pk, x25519_pk),
                 inference_types=excluded.inference_types,
                 updated_at=excluded.updated_at""",
            (
                peer.peer_id,
                peer.name,
                peer.api_host,
                peer.api_port,
                peer.token,
                peer.token_expires_at,
                peer.token_issued_at,
                peer.pubkey,
                peer.x25519_pk,
                # The DB mirrors discovery; the in-memory registry remains
                # the running process's source of truth.
                json.dumps(peer.inference_types),
                now,
                now,
            ),
        )
        con.commit()

    submit_db_write(_write)
