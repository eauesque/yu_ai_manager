"""App construction for web_ui runtime."""

import logging
from pathlib import Path

from jinja2 import ChoiceLoader, FileSystemLoader
from quart import Quart

from core.ui_core.resolver import get_ui_paths, resolve_active_ui
from core.web.app_factory import (
    register_blueprints,
    register_error_handlers,
    register_request_debug_hooks,
)

logger = logging.getLogger(__name__)


def create_app(db_path: Path, config: dict) -> Quart:
    """Create and configure Quart app with all blueprints."""
    from core.system.safe_mode import is_safe_mode

    safe_mode = is_safe_mode()
    active_ui = resolve_active_ui(config)
    ui_paths = get_ui_paths(active_ui)
    default_paths = get_ui_paths("default")
    # For non-default UIs, disable built-in static route so our fallback works
    use_static_fallback = active_ui != "default"
    from core.web.url_converters import ClampedIntConverter

    app = Quart(
        "web_ui",
        template_folder=str(ui_paths["template_folder"]),
        static_folder=str(ui_paths["static_folder"]) if not use_static_fallback else None,
    )
    # Register before blueprints: Werkzeug resolves converters at route-compile time.
    app.url_map.converters["int"] = ClampedIntConverter
    app.config["ACTIVE_UI"] = active_ui

    # Template & static fallback: active UI -> default UI
    # Allows sample/custom UIs to override only the files they need;
    # missing templates/static files are resolved from the default UI.
    if use_static_fallback:
        active_tpl = str(ui_paths["template_folder"])
        default_tpl = str(default_paths["template_folder"])
        app.jinja_loader = ChoiceLoader([  # pyright: ignore[reportAttributeAccessIssue]
            FileSystemLoader(active_tpl),
            FileSystemLoader(default_tpl),
        ])
        logger.info("Template fallback: %s -> default", active_ui)

        # Static file fallback route: active UI -> default UI
        _active_static = str(ui_paths["static_folder"])
        _default_static = str(default_paths["static_folder"])

        @app.route("/static/<path:filename>")
        async def _static_with_fallback(filename: str):
            from quart import send_from_directory
            if (Path(_active_static) / filename).exists():
                return await send_from_directory(_active_static, filename)
            return await send_from_directory(_default_static, filename)
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 86400
    app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB upload limit

    # Inject dist_v into all Jinja2 templates for cache-busting.
    # dist_v = first 8 chars of the src_hash written by build.mjs into
    # dist/.build-info.json.  Changes on every `pnpm run build` so browsers
    # automatically re-fetch dist/*.js after a rebuild + server restart.
    try:
        import json as _json
        _dist_info = (
            Path(ui_paths["static_folder"]) / "dist" / ".build-info.json"
        )
        if _dist_info.exists():
            _info = _json.loads(_dist_info.read_text(encoding="utf-8"))
            _dist_v = str(_info.get("src_hash", ""))[:8] or "dev"
        else:
            _dist_v = "dev"
    except Exception:
        _dist_v = "dev"
    app.jinja_env.globals["dist_v"] = _dist_v

    # Behind reverse proxy: apply ASGI ProxyFix middleware
    # Enabled when deploy.behind_proxy=true or trusted_proxy_ips is configured
    deploy_cfg = config.get("deploy", {})
    server_cfg = config.get("server", {})
    hsts_cfg = deploy_cfg.get("hsts", {}) if isinstance(deploy_cfg.get("hsts", {}), dict) else {}
    app.config["HSTS_ENABLED"] = bool(
        hsts_cfg.get("enabled", deploy_cfg.get("hsts_enabled", False))
    )
    app.config["HSTS_MAX_AGE"] = int(
        hsts_cfg.get("max_age", deploy_cfg.get("hsts_max_age", 31536000))
    )
    app.config["HSTS_INCLUDE_SUBDOMAINS"] = bool(
        hsts_cfg.get(
            "include_subdomains", deploy_cfg.get("hsts_include_subdomains", True)
        )
    )
    app.config["HSTS_PRELOAD"] = bool(
        hsts_cfg.get("preload", deploy_cfg.get("hsts_preload", False))
    )
    trusted_ips = set(server_cfg.get("trusted_proxy_ips", []))
    if deploy_cfg.get("behind_proxy", False) and not trusted_ips:
        # behind_proxy=true but trusted_proxy_ips not set -- trust loopback
        trusted_ips = {"127.0.0.1", "::1"}
    if trusted_ips:
        from core.web.proxy_fix import ProxyFixMiddleware
        app.asgi_app = ProxyFixMiddleware(app.asgi_app, trusted_ips)  # pyright: ignore[reportAttributeAccessIssue]

    # Register Extension core_shim early, before Blueprint registration
    # (routes import core.xxx_core at module level)
    from core.extensions_core.lifecycle.extensions_core_shim import register_all_core_shims
    register_all_core_shims()

    register_blueprints(app)
    register_request_debug_hooks(app)
    register_error_handlers(app)

    if not safe_mode:
        @app.before_serving
        async def _gateway_startup():
            import asyncio

            import core.paths
            from core.gateway import backend_registry
            from core.gateway.audit import init_writer
            from core.gateway.auth import get_auth, load_config_from_app_config
            from core.gateway.health_probe import BackendEntry, HealthProbe
            from core.gateway.status_log import gc_old_transitions
            from routes.gateway_status import set_probe

            get_auth().load_config(load_config_from_app_config(config))

            gw_cfg = config.get("gateway", {})
        # --- agentmemory proxy startup ---
            from core.gateway.agentmemory_proxy import (
                configure as configure_agentmemory,
            )
            from core.gateway.agentmemory_proxy import (
                validate_base_url as validate_am_url,
            )
            from core.settings_core.secret_store import decrypt as decrypt_secret
            am_cfg = gw_cfg.get("backends", {}).get("agentmemory", {})
            am_base_url = am_cfg.get("base_url", "http://127.0.0.1:3111")
            try:
                validate_am_url(am_base_url)
            except ValueError as exc:
                logger.error("[gateway:agentmemory] invalid base_url: %s", exc)
                raise
            am_secret_enc = am_cfg.get("secret_enc")
            am_secret = decrypt_secret(am_secret_enc) if am_secret_enc else None
        # Check if base_url is loopback; warn if not
            try:
                import ipaddress
                from urllib.parse import urlparse as _urlparse

                _host = _urlparse(am_base_url).hostname or ""
                _is_loopback = _host == "localhost" or (
                    bool(_host) and ipaddress.ip_address(_host).is_loopback
                )
            except ValueError:
                _is_loopback = False
            if not _is_loopback:
                logger.warning(
                    "[gateway:agentmemory] base_url %r is not loopback — "
                    "ensure agentmemory server itself does NOT bind to 0.0.0.0",
                    am_base_url,
                )
            configure_agentmemory(am_base_url, am_secret)

        # --- headroom proxy startup ---
            from core.gateway.headroom_proxy import configure as configure_headroom
            from core.gateway.headroom_proxy import configure_auth_key as configure_headroom_auth
            from core.gateway.headroom_proxy import validate_base_url as validate_hr_url
            hr_cfg = gw_cfg.get("backends", {}).get("headroom", {})
            hr_base_url = hr_cfg.get("base_url", "http://127.0.0.1:8787")
            try:
                validate_hr_url(hr_base_url)
            except ValueError as exc:
                logger.error("[gateway:headroom] invalid base_url: %s", exc)
                raise
            try:
                _host = _urlparse(hr_base_url).hostname or ""
                _is_loopback = _host == "localhost" or (
                    bool(_host) and ipaddress.ip_address(_host).is_loopback
                )
            except ValueError:
                _is_loopback = False
            if not _is_loopback:
                logger.warning(
                    "[gateway:headroom] base_url %r is not loopback — "
                    "ensure headroom server itself does NOT bind to 0.0.0.0",
                    hr_base_url,
                )
            configure_headroom(hr_base_url)
            configure_headroom_auth(decrypt_secret(str(hr_cfg.get("auth_key") or "")))

            log_dir = core.paths.data_path() / "logs" / "gateway"
            writer = init_writer(log_dir)
            await writer.start()

            backends = {
                k: BackendEntry(type=v.get("type", ""), base_url=v["base_url"])
                for k, v in gw_cfg.get("backends", {}).items()
                if "base_url" in v
            }
            backends.setdefault("agentmemory", BackendEntry(type="agentmemory", base_url=am_base_url))
            backends.setdefault("headroom", BackendEntry(type="headroom", base_url=hr_base_url))
            db_path = core.paths.data_path() / "tags.db"
            interval = gw_cfg.get("health_probe", {}).get("interval_seconds", 10)
            probe = HealthProbe(backends=backends, db_path=db_path, interval=interval)
            if gw_cfg.get("health_probe", {}).get("enabled", True):
                await probe.start()
            set_probe(probe)
            # Also publish it core-side so core modules (startup_background)
            # can read it without importing routes.
            backend_registry.set_probe(probe)
            app.extensions["gateway_probe"] = probe
            from core.gateway.scan import ScanRegistry
            app.extensions["gateway_scan_registry"] = ScanRegistry()
            try:
                # Offload sync SQLCipher DELETE (PBKDF2 connect ~250-500 ms on Pi)
                # to a worker thread so startup doesn't block the event loop.
                await asyncio.to_thread(gc_old_transitions, db_path)
            except Exception as exc:
                logger.warning("[gateway:gc] startup gc failed: %s", exc)

            async def _gc_loop():
                while True:
                    await asyncio.sleep(86400)
                    try:
                        await asyncio.to_thread(gc_old_transitions, db_path)
                    except Exception as e:
                        logger.warning("[gateway:gc] periodic gc failed: %s", e)
            app.extensions["gateway_gc"] = asyncio.create_task(_gc_loop(), name="gateway-gc")

        @app.after_serving
        async def _gateway_shutdown():
            import asyncio
            import contextlib

            from core.gateway.audit import get_writer
            writer = get_writer()
            if writer:
                await writer.stop()
            probe = app.extensions.get("gateway_probe")
            if probe:
                await probe.stop()
            gc_task = app.extensions.get("gateway_gc")
            if gc_task:
                gc_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await gc_task

    # Start mDNS once the asyncio loop is up. Deferred here because the
    # subsystem init runs before Quart binds the loop.
    if not safe_mode:
        @app.before_serving
        async def _start_mdns() -> None:
            from core.web.runtime_mdns import start_mdns_pending
            await start_mdns_pending()

        @app.after_serving
        async def _stop_mdns_sweep() -> None:
            from core.web.runtime_mdns import stop_mdns_pending
            await stop_mdns_pending()

    # Sweep history backfill (migration 68 follow-up). Idempotent — the
    # task self-checks `sweeps_backfill_done` and exits immediately on
    # second-and-later boots. First-time run trickles through the file
    # table at ~50 files/sec so it doesn't perturb interactive use.
    if not safe_mode:
        @app.before_serving
        async def _start_sweep_backfill() -> None:
            try:
                from core.bridge_core.sweep_backfill_task import schedule_sweep_backfill
                schedule_sweep_backfill()
            except Exception as exc:  # noqa: BLE001
                logger.warning("sweep backfill: schedule failed: %s", exc)

        @app.after_serving
        async def _stop_sweep_backfill() -> None:
            try:
                from core.bridge_core.sweep_backfill_task import stop_sweep_backfill
                stop_sweep_backfill()
            except Exception:  # noqa: BLE001
                logger.warning("web startup step failed", exc_info=True)

    # Close thread-local DB connections at end of each request to prevent
    # uncommitted implicit transactions from holding locks.
    @app.teardown_appcontext
    async def _close_db_connections(exc):
        from core.services_core.db_state import close_thread_connections
        close_thread_connections()

    return app
