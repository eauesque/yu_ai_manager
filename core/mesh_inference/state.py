"""Thread-safe mesh inference disabled overlay with durable backing.

The overlay is keyed by peer_id and is independent of PeerRegistry, so
mDNS re-discovery of the same peer cannot silently re-enable a disabled
inference type. Discovery-layer carry-over logic is therefore unneeded.
"""
from __future__ import annotations

import logging
import threading

from .peer_id import is_valid_peer_id

logger = logging.getLogger(__name__)


class MeshInferenceState:
    """Process-wide disabled overlay: {peer_id → set[inference_type]}.

    Reads stay in memory because dispatch consults this state frequently.
    Rows are persisted so restarts and native readers see the same overlay.
    Thread-safe via a single coarse lock — toggle traffic is user-initiated.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._disabled: dict[str, set[str]] = {}
        self.load_persisted()

    def load_persisted(self) -> None:
        try:
            from core.services_core.db_state import get_readonly_db

            rows = get_readonly_db().execute(
                "SELECT peer_id, inference_type FROM peer_inference_disabled"
            ).fetchall()
        except Exception as exc:
            logger.warning("[mesh_inference] loading disabled state failed: %s", exc)
            return
        with self._lock:
            self._disabled.clear()
            for peer_id, inference_type in rows:
                if is_valid_peer_id(peer_id) and isinstance(inference_type, str):
                    self._disabled.setdefault(peer_id, set()).add(inference_type)

    def is_disabled(self, peer_id: str, inference_type: str) -> bool:
        with self._lock:
            types = self._disabled.get(peer_id)
            return types is not None and inference_type in types

    def set_disabled(
        self, peer_id: str, inference_type: str, flag: bool
    ) -> None:
        if not is_valid_peer_id(peer_id):
            raise ValueError(f"invalid peer_id: {peer_id!r}")
        with self._lock:
            if flag:
                self._disabled.setdefault(peer_id, set()).add(inference_type)
            else:
                types = self._disabled.get(peer_id)
                if types is not None:
                    types.discard(inference_type)
                    if not types:
                        del self._disabled[peer_id]

        from core.services_core.db_write import submit_db_write

        def _write() -> None:
            from core.services_core.db_state import get_db

            con = get_db()
            if flag:
                con.execute(
                    "INSERT OR IGNORE INTO peer_inference_disabled "
                    "(peer_id, inference_type) VALUES (?, ?)",
                    (peer_id, inference_type),
                )
            else:
                con.execute(
                    "DELETE FROM peer_inference_disabled "
                    "WHERE peer_id = ? AND inference_type = ?",
                    (peer_id, inference_type),
                )
            con.commit()

        try:
            submit_db_write(_write)
        except RuntimeError as exc:
            logger.warning("[mesh_inference] persisting disabled state failed: %s", exc)

    def disabled_for(self, peer_id: str) -> set[str]:
        with self._lock:
            types = self._disabled.get(peer_id)
            return set(types) if types is not None else set()

    def snapshot(self) -> dict[str, list]:
        """Return a JSON-serializable deep copy (lists, not sets)."""
        with self._lock:
            return {pid: sorted(types) for pid, types in self._disabled.items()}

    def load(self, data: dict[str, list]) -> None:
        """Replace internal state from a persistence snapshot.

        Invalid peer_ids are skipped with a warning so a corrupt file
        does not prevent the rest of the state from loading.
        """
        with self._lock:
            self._disabled.clear()
            for pid, types in data.items():
                if not is_valid_peer_id(pid):
                    logger.warning(
                        "[mesh_inference] skipping invalid peer_id in state: %r",
                        pid,
                    )
                    continue
                if not isinstance(types, list):
                    continue
                clean = {t for t in types if isinstance(t, str)}
                if clean:
                    self._disabled[pid] = clean

    def clear(self) -> None:
        with self._lock:
            self._disabled.clear()


_state = MeshInferenceState()


def get_state() -> MeshInferenceState:
    """Module-level singleton accessor."""
    return _state
