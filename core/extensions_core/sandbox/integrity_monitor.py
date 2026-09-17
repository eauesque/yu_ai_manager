"""FileIntegrityMonitor: SHA-256 tamper detection for extension files.

Periodically checks file hashes in a daemon thread
and automatically revokes tokens when tampering is detected.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

# Default check interval (seconds)
_DEFAULT_INTERVAL = 300  # 5 minutes


class FileIntegrityMonitor:
    """SHA-256 tamper detection for extension files.

    Records baselines at startup and performs periodic checks.
    On tampering detection, automatically revokes tokens and notifies via event_bus.
    """

    def __init__(self, interval: float = _DEFAULT_INTERVAL) -> None:
        # ext_name -> {relative_path -> sha256_hex}
        self._baselines: dict[str, dict[str, str]] = {}
        # ext_name -> extension directory
        self._ext_dirs: dict[str, Path] = {}
        # Extensions with detected tampering
        self._tampered: set[str] = set()
        self._interval = interval
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def record_baseline(self, ext_name: str, ext_dir: Path) -> None:
        """Record SHA-256 baseline for extension files.

        Args:
            ext_name: Extension name
            ext_dir: Extension directory path
        """
        hashes: dict[str, str] = {}
        if not ext_dir.exists():
            return

        for py_file in ext_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            try:
                rel = str(py_file.relative_to(ext_dir))
                sha = hashlib.sha256(
                    py_file.read_bytes()
                ).hexdigest()
                hashes[rel] = sha
            except (OSError, ValueError):
                continue

        self._baselines[ext_name] = hashes
        self._ext_dirs[ext_name] = ext_dir
        logger.debug(
            "IntegrityMonitor: baseline recorded for %s (%d files)",
            ext_name,
            len(hashes),
        )

    def check_integrity(self, ext_name: str) -> list[str]:
        """Check file integrity for an extension.

        Returns:
            List of relative paths of tampered files. Empty means OK.
        """
        baseline = self._baselines.get(ext_name)
        ext_dir = self._ext_dirs.get(ext_name)
        if baseline is None or ext_dir is None:
            return []

        tampered: list[str] = []

        for rel_path, expected_hash in baseline.items():
            full_path = ext_dir / rel_path
            if not full_path.exists():
                tampered.append(f"{rel_path} (deleted)")
                continue
            try:
                current_hash = hashlib.sha256(
                    full_path.read_bytes()
                ).hexdigest()
                if current_hash != expected_hash:
                    tampered.append(rel_path)
            except OSError:
                tampered.append(f"{rel_path} (read error)")

        # Detect new files
        if ext_dir.exists():
            for py_file in ext_dir.rglob("*.py"):
                if "__pycache__" in str(py_file):
                    continue
                try:
                    rel = str(py_file.relative_to(ext_dir))
                    if rel not in baseline:
                        tampered.append(f"{rel} (new file)")
                except ValueError:
                    continue

        return tampered

    def start_periodic_check(self) -> None:
        """Start periodic checks in a daemon thread."""
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._check_loop,
            name="IntegrityMonitor",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "IntegrityMonitor: periodic check started (interval=%ds)",
            int(self._interval),
        )

    def stop(self) -> None:
        """Stop periodic checks."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("IntegrityMonitor: stopped")

    def _check_loop(self) -> None:
        """Main loop for periodic checks."""
        while not self._stop_event.wait(self._interval):
            self._run_check()
            self._check_inactivity()

    def _run_check(self) -> None:
        """Check file integrity for all extensions."""
        for ext_name in list(self._baselines.keys()):
            if ext_name in self._tampered:
                continue  # Already detected

            tampered = self.check_integrity(ext_name)
            if tampered:
                self._tampered.add(ext_name)
                logger.warning(
                    "IntegrityMonitor: tampering detected for '%s': %s",
                    ext_name,
                    tampered,
                )
                self._on_tampering_detected(ext_name, tampered)

    def _check_inactivity(self) -> None:
        """Check for inactivity timeout."""
        try:
            from core.extensions_core.token_mgmt.token_revocation import (
                get_revocation_tracker,
            )
            tracker = get_revocation_tracker()

            for ext_name in list(self._baselines.keys()):
                if ext_name in self._tampered:
                    continue
                should_revoke, reason = tracker.check_inactivity(ext_name)
                if should_revoke:
                    from core.extensions_core.token_mgmt.capability_token import (
                        get_enforcer,
                    )
                    enforcer = get_enforcer()
                    enforcer.revoke_tokens(ext_name)
                    logger.info(
                        "IntegrityMonitor: access revoked for '%s' (%s)",
                        ext_name,
                        reason,
                    )
        except Exception as exc:
            logger.debug("IntegrityMonitor: inactivity check failed: %s", exc)

    def _on_tampering_detected(self, ext_name: str, tampered_files: list[str]) -> None:
        """Handle tampering detection: revoke tokens + notify via event_bus."""
        # Immediately revoke tokens
        try:
            from core.extensions_core.token_mgmt.capability_token import get_enforcer
            enforcer = get_enforcer()
            enforcer.revoke_tokens(ext_name)
        except Exception as exc:
            logger.error(
                "IntegrityMonitor: revocation failed for '%s': %s",
                ext_name,
                exc,
            )

        # Notify via event_bus
        try:
            from core.extensions_core.service_registry import ServiceRegistry
            event_bus = ServiceRegistry.get("event_bus")
            if event_bus and hasattr(event_bus, "emit"):
                event_bus.emit("sandbox.token_revoked", {
                    "ext_name": ext_name,
                    "reason": "file_tampering",
                    "files": tampered_files[:10],  # Max 10 entries
                })
        except Exception:
            # Revocation stands; only the notice that tampering was found is lost.
            logger.warning(
                "tampering revocation event for %s was not emitted", ext_name, exc_info=True
            )

    def is_tampered(self, ext_name: str) -> bool:
        """Return whether tampering has been detected for an extension."""
        return ext_name in self._tampered

    def get_status(self, ext_name: str) -> dict:
        """Return the integrity status for an extension."""
        baseline = self._baselines.get(ext_name)
        return {
            "monitored": baseline is not None,
            "file_count": len(baseline) if baseline else 0,
            "tampered": ext_name in self._tampered,
            "tampered_files": self.check_integrity(ext_name) if baseline else [],
        }


# --- Singleton ---

_monitor: FileIntegrityMonitor | None = None


def get_integrity_monitor() -> FileIntegrityMonitor:
    """Return the singleton FileIntegrityMonitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = FileIntegrityMonitor()
    return _monitor


def reset_integrity_monitor() -> None:
    """For testing: reset the singleton."""
    global _monitor
    if _monitor is not None:
        _monitor.stop()
    _monitor = None
