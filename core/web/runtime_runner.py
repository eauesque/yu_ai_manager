"""Run loop for web_ui runtime."""

import logging
import os
import sys
from pathlib import Path

from core.web.runtime_runner_launch import finalize_and_run_app
from core.web.runtime_runner_platform import ensure_ssl_certs
from core.web.startup_background import build_background_tasks, mark_startup_task_skipped

logger = logging.getLogger(__name__)

from core.configuration.api import load_config, resolve_profile_config
from core.configuration.profiles import list_profiles
from core.configuration.profiles_migrate import ensure_profiles_ready
from core.extensions_core.lifecycle.runtime import init_extensions
from core.helpers_core.runtime_vendor_libs import ensure_vendor_libs
from core.services_core.db_api import init_app_state, set_boot_ready
from core.system.safe_mode import is_safe_mode
from core.web.runtime_app import create_app
from core.web.startup_args import (
    apply_debug_env_from_args,
    build_webui_parser,
    resolve_config_path,
    resolve_server_bind_and_pin,
)
from core.web.startup_db import check_db_schema_and_print_rescan
from core.web.startup_restart import apply_restart_config


def load_launch_args_file(
    project_root: Path,
    env: "os._Environ[str] | dict[str, str] | None" = None,
) -> list[str]:
    """Return extra argv parsed from launch-args.txt, or [] when absent/skipped.

    Honors YU_SKIP_LAUNCH_ARGS_FILE=1 so the test server can ignore the
    developer's launch-args.txt WITHOUT moving the real file (crash-safe).
    """
    env = os.environ if env is None else env
    if env.get("YU_SKIP_LAUNCH_ARGS_FILE") == "1":
        return []
    launch_args_file = project_root / "launch-args.txt"
    file_args: list[str] = []
    if launch_args_file.exists():
        for line in launch_args_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                file_args.extend(line.split())
    return file_args


def migrate_default_config(cfg_path: str | None, explicit_config: str | None) -> None:
    """Migrate only the default config selection; never alter --config."""
    if explicit_config:
        return
    try:
        from core.configuration.config_migrate import migrate_legacy_config
        migration = migrate_legacy_config(cfg_path)
        if migration["migrated"]:
            logger.info("Migrated legacy config keys %s; backup: %s", migration["merged_keys"], migration["backup"])
        elif migration["error"]:
            logger.warning("Legacy config migration failed: %s", migration["error"])
    except Exception:
        logger.warning("Legacy config migration failed", exc_info=True)


def run_web_ui() -> int:
    # Activate crash diagnostics before anything else so segfaults,
    # OOM kills, and unhandled exceptions leave traces in logs/.
    from core.infra_core.crash_log import setup_crash_log
    setup_crash_log()

    ensure_ssl_certs()
    parser = build_webui_parser()

    file_args = load_launch_args_file(Path(__file__).resolve().parents[2])
    if file_args:
        logger.info("  [ARGS] launch-args.txt: %s", " ".join(file_args))
    args = parser.parse_args(file_args + sys.argv[1:])
    apply_debug_env_from_args(args)
    safe_mode = is_safe_mode()

    db_path = Path(args.db)
    # Create data/ directory if it doesn't exist (first startup)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path = resolve_config_path(args.config)
    # Must happen before ANY load_config_json()/save_config_json() call that
    # omits an explicit path -- migrations and extension registration below
    # run before any Quart app/request context exists, so a context-based
    # resolution alone (current_app.config["CONFIG_PATH"]) misses all of
    # them and they fall back to the literal CWD-relative "config.json",
    # silently ignoring --config (see json_rw._default_config_path).
    if cfg_path:
        from core.configuration.json_rw import set_default_config_path
        set_default_config_path(cfg_path)
    migrate_default_config(cfg_path, args.config)
    config = load_config(cfg_path)

    # --- config.json "db" override (set via Settings > Change DB) ---
    # Only applies when --db was not explicitly specified on the command line
    config_db = config.get("db")
    _default_db = os.environ.get("TAGDB_DB", "data/tags.db")
    if config_db and isinstance(config_db, str) and args.db == _default_db:
        db_path = Path(config_db)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("DB path from config.json: %s", db_path)

    # --- Profile migration & directory setup ---
    ensure_profiles_ready()

    # --- Profile resolution ---
    profile_name = getattr(args, 'profile', None) or config.get("active_profile")
    profile_db_override = None
    if profile_name:
        try:
            config, profile_db_override = resolve_profile_config(config, profile_name)
        except ValueError as e:
            logger.error(f"{e}")
            return 1
        if profile_db_override:
            db_path = Path(profile_db_override)

    from core.infra_core.debug_log import log_startup_banner
    from core.search_api.server_info import APP_VERSION
    log_startup_banner(version=APP_VERSION, db_path=str(db_path))

    server_cfg = config.get("server", {})
    effective_host, effective_port, effective_pin, pin_source = resolve_server_bind_and_pin(args, server_cfg)
    from core.web.pin_policy import enforce_startup_pin_policy
    pin_policy_warn = enforce_startup_pin_policy(pin=effective_pin, pin_source=pin_source)
    # Back-fill the resolved port so subsystems (mDNS) advertise the actual
    # listening port even when --port overrides config["server"]["port"].
    config.setdefault("server", {})["port"] = effective_port

    from core.web.startup_mode import resolve_headless, resolve_server_mode
    mode = resolve_server_mode(args, server_cfg)
    headless = resolve_headless(args)
    if mode == "server":
        headless = True
    if mode != "full":
        logger.info("  [MODE] Server mode: %s", mode)

    trusted_proxy = server_cfg.get("trusted_proxy_auth", False) or getattr(args, 'trusted_proxy_auth', False)
    if effective_host == "0.0.0.0" and not effective_pin and not trusted_proxy:
        logger.error("[SECURITY] --pin is required when binding to 0.0.0.0 (LAN access).")
        logger.error("Use:  --pin <your-pin>  or set 'pin' in config.json server section.")
        return 1

    if effective_host == "0.0.0.0":
        from core.system.macos_firewall import ensure_lan_firewall_exception
        if not ensure_lan_firewall_exception(sys.executable):
            logger.error(
                "[FIREWALL] macOS firewall exception for the LAN port could not be "
                "set; the server would be unreachable from other machines. Aborting startup."
            )
            logger.error(
                "[FIREWALL] LANポートのファイアウォール許可に失敗しました。"
                "別マシンから到達不能になるため起動を中止します。"
            )
            return 1

    # Gateway and server modes can run without a database
    db_available = db_path.exists()
    if mode in ("gateway", "server") and not db_available:
        logger.info("  [MODE] %s mode: database not found, running without DB", mode)
        init_app_state(db_path, config)
    else:
        init_app_state(db_path, config)

        if not db_available:
            # No existing DB — create a fresh one via check_db_schema_and_print_rescan
            # (handles first-run of the NSIS installer where no DB exists yet)
            logger.info("Database not found at %s — creating new database.", db_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)
        if safe_mode:
            logger.info("  [SAFE MODE] automatic DB migration skipped")
        else:
            check_db_schema_and_print_rescan(db_path)
        # Re-check after potential creation so _no_db_guard is not registered
        db_available = db_path.exists()

    # Register Extension core_shim early
    from core.extensions_core.lifecycle.extensions_core_shim import register_all_core_shims
    register_all_core_shims()

    # Register core services in ServiceRegistry
    from core.extensions_core.service_registry_init import init_core_services
    init_core_services(db_path=db_path)

    if safe_mode:
        logger.info("  [SAFE MODE] vendor/GPU library initialization skipped")
    else:
        logger.info("Checking vendor libraries...")
        ensure_vendor_libs()

    from core.web.startup_build import maybe_install_deps, maybe_rebuild_ts
    if safe_mode:
        logger.info("  [SAFE MODE] dependency install and TS rebuild skipped")
    else:
        maybe_install_deps()
        maybe_rebuild_ts()

    # --- Background startup tasks (declarative) ---
    import threading

    from core.web.startup_mode import _should_run_bg_task

    background_tasks = build_background_tasks()

    # Export for /api/server/subsystems introspection
    from core.web.runtime_subsystems import BACKGROUND_TASKS as _bg_export
    _bg_export.clear()
    _bg_export.extend(background_tasks)

    # Warm up the main DB connection on this thread *before* spawning any
    # background thread. With the SHM (wal-index) created and attached cleanly
    # here, every subsequent open from background tasks / HTTP handlers
    # attaches to the same SHM inode rather than racing the first-connection
    # recovery branch — a SQLCipher 4.x WAL-mode race that corrupted the SHM
    # (lsof showed multiple connections holding (deleted) tags.db-shm inodes)
    # and surfaced as "database disk image is malformed" / "disk I/O error".
    if safe_mode:
        logger.info("  [SAFE MODE] DB warm-up skipped")
    else:
        try:
            from core.services_core.db_state_connections import warm_up_main_db
            warm_up_main_db()
        except Exception:
            logger.warning("DB warm-up failed; SHM-race protection may be reduced", exc_info=True)

    has_critical = False
    for task in background_tasks:
        if _should_run_bg_task(task, mode):
            logger.info("  [BG] %s starting", task.name)
            threading.Thread(target=task.target, name=f"startup-{task.name}", daemon=True).start()
            if task.critical:
                has_critical = True
        else:
            logger.info("  [BG] %s skipped (mode=%s)", task.name, mode)
            # Release any downstream tasks that wait on this one's
            # completion event (see startup_background._STARTUP_COMPLETION_EVENTS).
            mark_startup_task_skipped(task.name)

    if not has_critical:
        set_boot_ready()

    app = create_app(db_path, config)
    app.config["SERVER_MODE"] = mode
    app.config["HEADLESS"] = headless
    app.config["DB_AVAILABLE"] = db_available
    app.config["PIN_SOURCE"] = pin_source
    app.config["PIN_POLICY_WARN"] = pin_policy_warn
    app.config["CONFIG_PATH"] = str(cfg_path)
    app.config["PORT"] = effective_port
    app.config["HOST"] = effective_host
    app.config["SAFE_MODE"] = safe_mode
    apply_restart_config(app, args, server_cfg)

    # Attach log ring buffer handler to root logger (deferred to avoid
    # interfering with werkzeug's StreamHandler detection).
    from core.infra_core.log_ring_buffer import RingBufferHandler, log_ring

    @app.before_request
    def _install_ring_handler_once():
        if getattr(app, '_ring_handler_installed', False):
            return
        app._ring_handler_installed = True  # pyright: ignore[reportAttributeAccessIssue]
        _rh = RingBufferHandler(log_ring)
        _rh.setFormatter(logging.Formatter("%(message)s"))
        root = logging.getLogger()
        root.addHandler(_rh)
        # Ensure root logger passes INFO+ to handlers (default is WARNING).
        # Individual handlers still control their own output level.
        if root.level > logging.INFO:
            root.setLevel(logging.INFO)

    from core.scan_core.scanner import set_extension_manager
    from core.web.auth_setup import setup_auth

    if getattr(args, 'trusted_proxy_auth', False):
        server_cfg["trusted_proxy_auth"] = True

    setup_auth(app, effective_pin, server_cfg)

    # Block DB-dependent routes when DB is not available (gateway without DB)
    if not db_available:
        # Routes that work without DB
        _NO_DB_ALLOWED = (
            "/api/server/", "/api/settings/llm-endpoints", "/api/llm/",
            "/api/events/", "/api/jobs/status", "/api/server-info",
            "/v1/", "/ext/hailo-genai/", "/ext/hailo-yolo/",
            "/ext/speech-to-text/",
            "/static/", "/api/auth/", "/api/pin/",
        )
        from quart import request as _req_nodb
        @app.before_request
        async def _no_db_guard():
            path = _req_nodb.path
            if path == "/":
                return  # Allow index page
            if any(path.startswith(p) for p in _NO_DB_ALLOWED):
                return
            if not path.startswith("/api/") and "/api/" not in path:
                return  # Allow non-API pages (CSS, JS, templates)
            from core.infra_core.api_errors import api_error
            return api_error("Database not available (gateway mode without DB)", 503, code="gateway_no_db")

    if headless:
        from quart import request as _request
        @app.before_request
        async def _headless_guard():
            path = _request.path
            if (path.startswith("/api/") or
                path.startswith("/v1/") or
                "/api/" in path or
                path.startswith("/static/")):
                return
            return "Not Found", 404

    app.config["ACTIVE_PROFILE"] = profile_name
    app.config["PROFILES"] = {p["name"]: p for p in list_profiles()}

    # Ensure startup tasks that hold raw-connection write locks (analyze,
    # file_meta_cache) have finished before extension DB migrations run.
    # ALTER TABLE needs exclusive lock; concurrent raw writers cause
    # "database is locked" after busy_timeout. Same pattern as
    # _startup_tag_normalize_backfill. v4.199.3
    from core.web.startup_background import wait_for_db_writers
    if safe_mode:
        logger.info("  [SAFE MODE] extension loading skipped")
    else:
        wait_for_db_writers()

        ext_dir = Path(config.get("extensions_dir", "extensions"))
        ext_mgr = init_extensions(ext_dir)
        set_extension_manager(ext_mgr)
        for bp, prefix in ext_mgr.get_blueprints():
            try:
                app.register_blueprint(bp, url_prefix=prefix)
                logger.info(f"  Extension Blueprint: {prefix}")
            except Exception as e:
                logger.error(f"Extension Blueprint registration failed: {e}")

    from core.infra_core.ai_context import check_blueprint_drift
    check_blueprint_drift(set(app.blueprints.keys()))

    return finalize_and_run_app(
        app,
        args=args,
        config=config,
        server_cfg=server_cfg,
        mode=mode,
        db_path=db_path,
        effective_host=effective_host,
        effective_port=effective_port,
        effective_pin=effective_pin,
        profile_name=profile_name,
    )
