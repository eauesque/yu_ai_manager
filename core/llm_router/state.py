"""In-memory thread-safe backend catalog for the LLM router."""

from __future__ import annotations

import threading
from datetime import UTC

from .models import BackendInfo, ModelInfo


class BackendCatalog:
    """Process-wide cache of backend definitions, models, aliases, and metadata.

    Thread-safe via a single coarse lock -- discovery and dispatch run on
    different asyncio tasks but the catalog is the only shared state.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._backends: dict[str, BackendInfo] = {}
        self._aliases: dict[str, str] = {}
        self._metadata: dict[str, dict] = {}
        # Persisted disabled aliases that have no matching backend yet.
        # Consumed lazily by set_backend() when a matching alias is registered
        # (typically after mDNS discovery completes post-startup). Without
        # this, persisted disable state is lost for dynamically discovered
        # backends — see P4 regression test.
        self._pending_disabled: set[str] = set()

    def set_backend(self, info: BackendInfo) -> None:
        with self._lock:
            existing = self._backends.get(info.alias)
            # Carry over the UI-level disabled flag across discovery upserts.
            # Without this, probe_loop / mDNS re-registration silently re-enables
            # backends that an operator explicitly disabled from the WebUI.
            if existing is not None and existing.disabled:
                info.disabled = True
            # Apply any persisted-but-deferred disable for this alias
            # (e.g. mDNS backend that didn't exist at load_state() time).
            elif info.alias in self._pending_disabled:
                info.disabled = True
                self._pending_disabled.discard(info.alias)
            self._backends[info.alias] = info

    def set_disabled(self, alias: str, disabled: bool) -> bool:
        """Toggle the disabled flag on an existing backend.

        Returns True if the backend exists (and the flag was applied), False
        if no backend matches the alias. In the False case, when disabled=True,
        the alias is parked in ``_pending_disabled`` so the flag is re-applied
        when set_backend() registers a matching entry later.
        """
        with self._lock:
            backend = self._backends.get(alias)
            if backend is None:
                if disabled:
                    self._pending_disabled.add(alias)
                else:
                    self._pending_disabled.discard(alias)
                return False
            backend.disabled = disabled
            return True

    def list_disabled_aliases(self) -> list[str]:
        """Return all backend aliases that are currently disabled.

        Used by persistence.save_disabled_aliases() to snapshot state."""
        with self._lock:
            return [b.alias for b in self._backends.values() if b.disabled]

    def get_backend(self, alias: str) -> BackendInfo | None:
        with self._lock:
            return self._backends.get(alias)

    def list_backends(self) -> list[BackendInfo]:
        with self._lock:
            return list(self._backends.values())

    def set_aliases(self, aliases: dict[str, str]) -> None:
        with self._lock:
            self._aliases = dict(aliases)

    def resolve_alias(self, name: str) -> str | None:
        with self._lock:
            return self._aliases.get(name)

    def list_aliases(self) -> dict[str, str]:
        with self._lock:
            return dict(self._aliases)

    def find_model(self, physical_id: str) -> ModelInfo | None:
        """Look up a model by its full physical id (e.g. 'ollama-mac/qwen2.5:7b')."""
        if "/" not in physical_id:
            return None
        alias, _, model_name = physical_id.partition("/")
        with self._lock:
            backend = self._backends.get(alias)
            if backend is None:
                return None
            for m in backend.models:
                if m.name == model_name:
                    return m
            return None

    def set_metadata(self, physical_id: str, metadata: dict) -> None:
        with self._lock:
            self._metadata[physical_id] = dict(metadata)

    def get_metadata(self, physical_id: str) -> dict | None:
        with self._lock:
            meta = self._metadata.get(physical_id)
            return dict(meta) if meta is not None else None

    def remove_backend(self, alias: str) -> bool:
        """Remove a backend entirely from the catalog.

        Also cleans up related aliases and metadata entries.
        Returns True if the backend existed and was removed.
        """
        with self._lock:
            if alias not in self._backends:
                return False
            del self._backends[alias]
            self._pending_disabled.discard(alias)
            # Remove aliases that point to this backend
            stale_alias_keys = [
                k for k, v in self._aliases.items() if v == alias
            ]
            for k in stale_alias_keys:
                del self._aliases[k]
            # Remove metadata entries with this alias prefix
            stale_meta_keys = [
                k for k in self._metadata if k.startswith(f"{alias}/")
            ]
            for k in stale_meta_keys:
                del self._metadata[k]
            return True

    def purge_stale(self, *, max_age_sec: float = 86400) -> list[str]:
        """Remove auto-discovered backends that have been unreachable for too long.

        Only removes backends with ``auto_discover=True`` and
        ``status="unreachable"`` whose ``last_seen_at`` is older than
        *max_age_sec* (default 24 hours). Static/user-configured backends
        are never purged.

        Returns a list of removed aliases.
        """
        from datetime import datetime

        now = datetime.now(UTC)
        cutoff = now.timestamp() - max_age_sec
        removed: list[str] = []

        with self._lock:
            for alias, backend in list(self._backends.items()):
                if not backend.auto_discover:
                    continue
                if backend.status != "unreachable":
                    continue
                # Parse ISO 8601 last_seen_at
                seen_at = backend.last_seen_at
                if not seen_at:
                    # No timestamp — treat as stale
                    ts = 0.0
                else:
                    try:
                        dt = datetime.fromisoformat(seen_at.replace("Z", "+00:00"))
                        ts = dt.timestamp()
                    except (ValueError, TypeError):
                        ts = 0.0
                if ts < cutoff:
                    del self._backends[alias]
                    self._pending_disabled.discard(alias)
                    removed.append(alias)

        return removed

    def clear(self) -> None:
        """Test helper -- drop all state."""
        with self._lock:
            self._backends.clear()
            self._aliases.clear()
            self._metadata.clear()


_catalog = BackendCatalog()


def get_catalog() -> BackendCatalog:
    """Module-level singleton accessor."""
    return _catalog
