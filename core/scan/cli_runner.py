"""CLI-side facade over the WebUI background scan runtime.

The CLI used to run its own legacy scan loop (`legacy_scan*.py` +
`tagdb_core/scan_metadata/`), which had two problems:

1. It didn't initialize the extension manager, so on_scan_file hooks
   (ComfyUI / NovelAI / A1111) never fired during CLI scans.
2. Its internal extractors lagged behind the ones exercised by WebUI
   scans, so newer formats (FLAC ComfyUI metadata, MMAudioSampler, ...)
   weren't recognized when scanned via CLI.

This module wires up the same boot sequence the web server runs at
startup, then delegates to ``run_scan_background`` so CLI and WebUI
share one scan engine.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from core.jobs_core.jobs_model import Job

logger = logging.getLogger(__name__)


class _CLIScanJob(Job):
    """Job stub that mirrors progress/update calls to the console.

    `run_scan_background` and `execute_scan_loop` interact with the job
    purely through documented methods (update / progress / complete /
    complete_cancelled / fail / set_completion_data), so we just extend
    Job and emit log lines from those overrides.
    """

    def __init__(self):
        super().__init__("cli-scan", "CLI scan")
        self._last_logged_percent = -1
        self._last_logged_phase = ""

    def update(self, phase: str = "", message: str = "") -> None:
        super().update(phase=phase, message=message)
        if phase and phase != self._last_logged_phase:
            self._last_logged_phase = phase
            if message:
                logger.info("[%s] %s", phase, message)
            else:
                logger.info("[%s]", phase)
        elif message:
            logger.info("%s", message)

    def progress(self, current: int, total: int, detail: str = "") -> None:
        super().progress(current, total, detail)
        if total <= 0:
            return
        # Throttle: only log when the integer percent advances.
        if self.percent != self._last_logged_percent:
            self._last_logged_percent = self.percent
            logger.info("[%3d%%] %d / %d  %s", self.percent, current, total, detail or "")

    def complete(self, message: str = "") -> None:
        super().complete(message=message)
        logger.info("complete: %s", message or "(done)")

    def complete_cancelled(self, message: str = "") -> None:
        super().complete_cancelled(message=message)
        logger.info("cancelled: %s", message)

    def fail(self, error: str) -> None:
        super().fail(error)
        logger.error("scan failed: %s", error)

    def set_completion_data(self, **kwargs: Any) -> None:
        # WebUI uses this to ship added/updated/deleted id lists to the
        # client; for CLI we just summarize counts.
        for key in ("added_ids", "updated_ids", "deleted_ids"):
            ids = kwargs.get(key)
            if ids is not None:
                logger.info("%s: %d", key, len(ids))


def _bootstrap_runtime(db_path: Path, config: dict[str, Any]) -> None:
    """Replicate the subset of `runtime_runner._main_async` boot steps
    that the scan engine actually depends on.
    """
    from core.extensions_core.lifecycle.extensions_core_shim import register_all_core_shims
    from core.extensions_core.lifecycle.runtime import init_extensions
    from core.extensions_core.service_registry_init import init_core_services
    from core.paths import init_app_paths
    from core.scan_core.scanner import set_extension_manager
    from core.services_core.app_runtime_state import init_app_state

    # init_app_paths must run before any code that touches cache/log/profiles
    # dirs (post-scan maintenance reads cache_dir, etc.).
    init_app_paths()
    init_app_state(db_path, config)
    register_all_core_shims()
    init_core_services(db_path=db_path)

    ext_dir = Path(config.get("extensions_dir", "extensions"))
    ext_mgr = init_extensions(ext_dir)
    set_extension_manager(ext_mgr)


def _ensure_logging() -> None:
    """Make sure logger.info from the scan engine reaches stdout.

    The CLI doesn't go through Hypercorn's logger setup, so without an
    explicit basicConfig nothing prints. We also force UTF-8 on stdout
    so Japanese phase messages render correctly on Windows consoles
    (default cp932 mojibakes 削除済みファイル -> garbage).
    """
    import contextlib
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s",
                                           datefmt="%H:%M:%S"))
    root.addHandler(handler)
    if root.level > logging.INFO or root.level == logging.NOTSET:
        root.setLevel(logging.INFO)


def run_scan_cli(
    *,
    db_path: Path,
    root_path: str,
    recursive: bool,
    force: bool,
    scan_zips: bool = False,
    compute_hash_explicit: bool = False,
    config: dict[str, Any] | None = None,
) -> int:
    """Run a synchronous scan that shares the WebUI scan engine.

    Returns 0 on success, non-zero on failure (used as CLI exit code).
    """
    from core.configuration.api import load_config
    from core.scan.runtime import run_scan_background

    _ensure_logging()

    if config is None:
        config = load_config(None)

    _bootstrap_runtime(db_path, config)

    job = _CLIScanJob()
    try:
        run_scan_background(
            root_path=root_path,
            recursive=recursive,
            force=force,
            scan_zips=scan_zips,
            job=job,
            compute_hash_explicit=compute_hash_explicit,
            resume=False,
        )
    except Exception as e:
        logger.exception("scan crashed: %s", e)
        return 1
    finally:
        _drain_post_scan_threads()

    if job.error:
        return 2
    if job.cancelled and not job.running:
        return 3
    return 0


def _drain_post_scan_threads() -> None:
    """Wait briefly for the daemon `scan-post-maintenance` thread.

    `finalize_scan_runtime` spawns an async maintenance thread that runs
    FTS optimize + WAL checkpoint via the shared db-writer executor. In
    a short-lived CLI the process can exit before those tasks land,
    producing "cannot schedule new futures after shutdown" warnings.
    Wait up to a few seconds so the optimizations actually complete.
    """
    import threading
    import time

    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        worker = next(
            (t for t in threading.enumerate() if t.name == "scan-post-maintenance"),
            None,
        )
        if worker is None or not worker.is_alive():
            return
        worker.join(timeout=1.0)


__all__ = ["run_scan_cli"]
