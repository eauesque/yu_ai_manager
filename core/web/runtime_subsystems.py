"""Subsystem initialization for the web_ui runtime.

Extracted from runtime_runner to keep each module under 300 lines.
Called by run_web_ui() after the app is created.
"""

import logging
import threading

logger = logging.getLogger(__name__)


def init_event_bus_and_webhooks(config: dict) -> None:
    """Initialize Event Bus, SSE, and Webhook subsystems."""
    from core.webhook import webhook_dispatcher
    from core.webhook.webhook_routes import init_webhook_routes
    webhook_dispatcher.start()
    init_webhook_routes(webhook_dispatcher)
    # NOTE: Inbound webhook Blueprint is registered via routes/events.py
    # (not here — current_app is unavailable outside app context)

    # Purge old webhook delivery logs.
    # Deferred 60s + chunked on the writer thread to avoid competing with critical
    # startup writes; a single DELETE can take 10s+ when many rows have accumulated.
    def _deferred_webhook_purge() -> None:
        import time
        time.sleep(60)
        try:
            from core.webhook.webhook_delivery_log import purge_old_deliveries
            purge_old_deliveries(max_age_days=7)
        except Exception as exc:
            # Intentional: log purge is a housekeeping operation; failure must not impact runtime.
            logger.debug("  [WEBHOOK] Log purge skipped: %s", exc)
    threading.Thread(
        target=_deferred_webhook_purge,
        name="webhook-log-purge",
        daemon=True,
    ).start()


def log_interrupted_scan() -> None:
    """Log interrupted scan state if present (kept for resume banner)."""
    from core.scan_core.scan_state import load_scan_state
    _prev_scan = load_scan_state()
    if _prev_scan:
        _root = _prev_scan.get("root", "?")
        _cur = _prev_scan.get("current", 0)
        _tot = _prev_scan.get("total", 0)
        logger.info(f"  [SCAN] Interrupted scan state found: {_root} ({_cur}/{_tot})")


def init_backup_system(config: dict) -> None:
    """Initialize backup scheduler and event handlers."""
    try:
        from importlib import import_module
        _bk_evt = import_module("extensions.builtin_backup.core_impl.event_handler")
        subscribe_backup_events = _bk_evt.subscribe_backup_events
        _bk_sched = import_module("extensions.builtin_backup.core_impl.scheduler")
        backup_scheduler = _bk_sched.backup_scheduler

        backup_cfg = config.get("backup", {})
        if backup_cfg.get("enabled", True):
            subscribe_backup_events()
            interval = backup_cfg.get("periodic_interval_hours", 24)
            if interval > 0:
                backup_scheduler.start(interval)
                logger.info(f"  [BACKUP] Scheduler started (every {interval}h)")
            else:
                logger.info("  [BACKUP] Periodic backup disabled")
        else:
            logger.info("  [BACKUP] Backup system disabled")
    except Exception as exc:
        # Intentional: backup is an optional extension; server runs without it.
        logger.error(f"[BACKUP] Init failed: {exc}")


def init_task_scheduler(config: dict) -> None:
    """Initialize APScheduler task scheduler."""
    try:
        from core.scheduler_core import scheduler_manager
        sched_cfg = config.get("scheduler", {})
        if sched_cfg.get("enabled", True):
            scheduler_manager.start(sched_cfg)
            logger.info("  [SCHEDULER] Task scheduler started")
        else:
            logger.info("  [SCHEDULER] Task scheduler disabled")
    except Exception as exc:
        # Intentional: scheduled jobs are optional; missing scheduler does not affect core functions.
        logger.error(f"[SCHEDULER] Init failed: {exc}")


def init_security_subsystems() -> None:
    """Initialize key provider warmup and secret migration."""
    # Key provider pre-warm (avoid keyring timeout on first-use)
    try:
        from core.settings_core.key_provider import warmup as key_warmup
        key_warmup()
    except Exception as exc:
        # Intentional: warmup is an optimisation; keys still work on first real access.
        logger.debug("  [SECURITY] Key provider warmup skipped: %s", exc)

    # Migrate plaintext secrets to encrypted storage
    try:
        from core.settings_core.secret_store import migrate_plaintext_secrets
        migrated = migrate_plaintext_secrets()
        if migrated > 0:
            logger.info("Migrated %d plaintext secrets to encrypted", migrated)
    except Exception as exc:
        # Intentional: migration is opportunistic; plaintext secrets remain readable and retry
        # will run on the next startup.
        logger.debug("  [SECURITY] Secret migration skipped: %s", exc)  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure


def init_event_handlers() -> None:
    """Register semantic search, YOLO, and thumbnail event handlers."""
    # Semantic search event handler
    try:
        from core.clip_core.event_handler import subscribe_semantic_events
        subscribe_semantic_events()
        logger.info("  [SEMANTIC] Event handlers registered")
    except Exception as exc:
        # Intentional: CLIP/semantic search is an optional feature; absent on devices without
        # the model or the builtin-clip-search extension.
        logger.info(f"  [SEMANTIC] Init skipped: {exc}")

    # YOLO detection event handler
    try:
        from importlib import import_module
        _yolo_evt = import_module("extensions.builtin_hailo_yolo_detect.core_impl.event_handler")
        subscribe_yolo_events = _yolo_evt.subscribe_yolo_events
        subscribe_yolo_events()
        logger.info("  [YOLO] Event handlers registered")
    except Exception as exc:
        # Intentional: YOLO detection is a Hailo-only optional feature.
        logger.info(f"  [YOLO] Init skipped: {exc}")

    # Thumbnail pre-warm event handler
    try:
        from core.files_core.thumbnail_prewarm import subscribe_thumbnail_prewarm_events
        subscribe_thumbnail_prewarm_events()
        logger.info("  [THUMBNAIL] Pre-warm event handlers registered")
    except Exception as exc:
        # Intentional: thumbnail pre-warming is a performance hint; missing it causes
        # on-demand generation instead.
        logger.info(f"  [THUMBNAIL] Pre-warm init skipped: {exc}")

    # Preload image processing libraries (eliminate first-request latency)
    try:
        from core.files_core.thumbnail_preload import preload_image_libs
        preload_image_libs()
    except Exception as exc:
        # Intentional: preload is a latency optimisation; a cold first request is acceptable.
        logger.debug(f"  [THUMBNAIL] Preload skipped: {exc}")


def init_scan_queue() -> None:
    """Register scan launchers and resume pending scans."""
    # Scan queue consumer: register scan launchers
    try:
        from core.scan_api.ops_runtime import _start_worker_and_bridge
        from core.scan_core.scan_queue_consumer import register_scan_launchers
        from core.scan_roots_api.scan_all import run_scan_all_background
        register_scan_launchers(
            single=_start_worker_and_bridge,
            scan_all=run_scan_all_background,
        )
    except Exception as exc:
        # Intentional: scan queue is optional; manual scan from UI still works.
        logger.info(f"  [SCAN] Queue launcher registration skipped: {exc}")

    # Scan worker reconnect
    try:
        from routes.scan_api.ops_runtime import reconnect_running_worker
        if reconnect_running_worker():
            logger.info("  [SCAN] Reconnected to running scan worker")
    except Exception as exc:
        # Intentional: reconnect is best-effort; the scan worker will be re-launched on next request.
        logger.info(f"  [SCAN] Worker reconnect skipped: {exc}")

    # Scan queue: resume pending items if no scan is running.
    # Delayed by 15 seconds to avoid competing with startup I/O.
    try:
        from core.scan_core.scan_queue import scan_queue
        pending = scan_queue.size()
        if pending > 0:
            from core.jobs_core.jobs import job_manager
            if not job_manager.is_running("scan"):
                def _delayed_scan_resume():
                    import time
                    time.sleep(15)
                    try:
                        from core.scan_core.scan_queue_consumer import consume_next_queued_scan
                        consume_next_queued_scan()
                    except Exception as exc:
                        # Intentional: delayed resume runs in a daemon thread; failure is non-critical.
                        logger.debug("Delayed scan resume failed: %s", exc)
                threading.Thread(
                    target=_delayed_scan_resume,
                    daemon=True,
                    name="scan-queue-resume",
                ).start()
                logger.info(f"  [SCAN] Queue: {pending} pending scan(s) will resume in 15s")
            else:
                logger.info(f"  [SCAN] Queue: {pending} item(s) pending (scan active)")
    except Exception as exc:
        # Intentional: queue resume is opportunistic; pending scans remain queued for next startup.
        logger.info(f"  [SCAN] Queue resume skipped: {exc}")


def start_sse_server(effective_host: str, effective_port: int) -> None:
    """Start dedicated SSE server."""
    try:
        from core.sse import sse_broadcaster
        from core.sse.sse_server import start_sse_server as _start_sse
        sse_port = _start_sse(effective_host, effective_port, sse_broadcaster)
        if sse_port:
            logger.info(f"  [SSE] 専用サーバー: http://{effective_host}:{sse_port}/stream")
        else:
            logger.info("  [SSE] 専用サーバー未起動。従来の Flask Generator 方式で動作")
    except Exception as exc:
        # Intentional: SSE server is optional; the system falls back to the traditional
        # Flask generator approach automatically.
        logger.warning(f"  [SSE] 専用サーバー起動失敗: {exc}。フォールバック")


def start_sse_forwarder() -> None:
    """Forward event_bus events to the Rust SSE hub."""
    try:
        from core.sse.forwarder import start_sse_forwarder as _start
        _start()
        logger.info("  [SSE] Forwarder → Rust hub 起動")
    except Exception as exc:
        # Intentional: forwarder is optional; missing Rust hub is a normal non-Rust deployment.
        logger.debug("  [SSE] Forwarder 起動スキップ: %s", exc)


def schedule_faststart_prescan() -> None:
    """Run faststart pre-processing 60 seconds after server startup.

    Delayed from 10s to 60s to avoid competing with user requests
    during the critical first-minute startup window.
    """
    def _deferred_faststart_prescan():
        import time
        time.sleep(60)
        try:
            from core.files_core.faststart_prescan import start_faststart_prescan
            start_faststart_prescan()
        except Exception as exc:
            # Intentional: faststart is a background optimisation; missing it is harmless.
            logger.debug("Startup faststart prescan skipped: %s", exc)

    threading.Thread(
        target=_deferred_faststart_prescan,
        name="startup-faststart-prescan",
        daemon=True,
    ).start()


# ---------------------------------------------------------------------------
# Declarative subsystem / background-task definitions
# ---------------------------------------------------------------------------
from core.web.runtime_llm_router import (
    init_llm_router_discovery,
)
from core.web.runtime_mdns import (
    init_mdns_service,
    init_node_identity,
)
from core.web.startup_mode import BackgroundTaskDef, SubsystemDef


def _log_interrupted_scan_wrapper(config: dict) -> None:
    log_interrupted_scan()

def _security_wrapper(config: dict) -> None:
    init_security_subsystems()

def _event_handlers_wrapper(config: dict) -> None:
    init_event_handlers()

def _scan_queue_wrapper(config: dict) -> None:
    init_scan_queue()
    try:
        from core.scan_core.scan_history import init as init_scan_history
        init_scan_history()
    except Exception as exc:
        # Intentional: scan history is metadata-only; core scan functionality is unaffected.
        logger.info("  [SCAN] History init skipped: %s", exc)


SUBSYSTEMS: list[SubsystemDef] = [
    SubsystemDef("event_bus",       ["full", "gateway", "server"], init_event_bus_and_webhooks),
    SubsystemDef("log_interrupted", ["full"],                      _log_interrupted_scan_wrapper),
    SubsystemDef("backup",          ["full"],                      init_backup_system,
                 env_override="TAGDB_ENABLE_BACKUP"),
    SubsystemDef("scheduler",       ["full"],                      init_task_scheduler,
                 env_override="TAGDB_ENABLE_SCHEDULER"),
    SubsystemDef("security",        ["full", "gateway", "server"], _security_wrapper),
    SubsystemDef("event_handlers",  ["full", "gateway", "server"], _event_handlers_wrapper),
    SubsystemDef("scan_queue",      ["full"],                      _scan_queue_wrapper,
                 env_override="TAGDB_ENABLE_SCAN"),
    SubsystemDef("node_identity",   ["full", "gateway", "server"], init_node_identity),
    SubsystemDef("llm_router",      ["full", "gateway", "server"], init_llm_router_discovery),
    SubsystemDef("mdns",            ["full", "gateway", "server"], init_mdns_service,
                 env_override="TAGDB_ENABLE_MDNS"),
]

# Populated by runtime_runner.py at startup for API introspection
BACKGROUND_TASKS: list[BackgroundTaskDef] = []
