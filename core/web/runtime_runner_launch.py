"""Late-stage app launch and subsystem wiring for web_ui."""

from __future__ import annotations

import asyncio
import inspect
import logging

from core.infra_core.debug_log import get_debug_log_path, is_debug_enabled
from core.web.runtime_runner_platform import kill_stale_port
from core.web.startup_banner import print_startup_banner

logger = logging.getLogger(__name__)


def finalize_and_run_app(
    app,
    *,
    args,
    config: dict,
    server_cfg: dict,
    mode: str,
    db_path,
    effective_host: str,
    effective_port: int,
    effective_pin: str | None,
    profile_name,
) -> int:
    from core.system.safe_mode import is_safe_mode
    from core.web.runtime_subsystems import (
        SUBSYSTEMS,
        schedule_faststart_prescan,
        start_sse_forwarder,
        start_sse_server,
    )
    from core.web.startup_mode import _env_truthy, _should_run_subsystem

    for sub in SUBSYSTEMS:
        if _should_run_subsystem(sub, mode):
            logger.info("  [INIT] %s", sub.name)
            result = sub.init(config)
            if inspect.iscoroutine(result):
                asyncio.run(result)
        else:
            logger.info("  [SKIP] %s (mode=%s)", sub.name, mode)

    print_startup_banner(
        db_path,
        effective_host,
        effective_port,
        effective_pin,
        profile_name=profile_name,
        profiles=app.config["PROFILES"],
    )
    if app.config.get("TRUSTED_PROXY_AUTH"):
        header = app.config.get("TRUSTED_PROXY_HEADER", "X-Remote-User")
        ips = ", ".join(sorted(app.config.get("TRUSTED_PROXY_IPS", set())))
        logger.info(f"  [AUTH] Trusted proxy auth: {header} from {ips}")
    logger.info("")
    logger.info("  [CRASH] Crash diagnostics: logs/crash.log, logs/faulthandler.log")
    if is_debug_enabled():
        logger.info(f"  [DEBUG] Structured debug log: {get_debug_log_path()}")
    logger.info("")

    from core.platform import install_proactor_connection_reset_silencer, install_sigint_handler

    install_proactor_connection_reset_silencer()
    install_sigint_handler()
    kill_stale_port(effective_port)

    if not is_safe_mode():
        start_sse_server(effective_host, effective_port)
        start_sse_forwarder()
    else:
        logger.info("  [SAFE MODE] SSE server skipped")
    if not is_safe_mode() and (mode == "full" or _env_truthy("TAGDB_ENABLE_SCAN")):
        schedule_faststart_prescan()

    from core.web.shutdown import register_shutdown

    register_shutdown(app)

    # Register before_serving hook for inference worker event loop binding
    if not is_safe_mode():
        _register_before_serving_hooks(app, config)
    else:
        logger.info("  [SAFE MODE] inference worker hooks skipped")

    debug_enabled = args.debug and not (
        effective_host in ("0.0.0.0", "::") or server_cfg.get("lan")
    )
    app.run(
        host=effective_host,
        port=effective_port,
        debug=debug_enabled,
        use_reloader=False,
    )
    return 0


def _register_before_serving_hooks(app, config: dict) -> None:
    """Register before_serving hooks for subsystems that need the event loop."""
    # LLM subprocess: bind event loop to inference bridge for streaming token dispatch
    hailo_genai_cfg = config.get("hailo_genai", {})
    if hailo_genai_cfg.get("llm_subprocess", False):
        # Validate that inference_worker is enabled
        inference_worker_cfg = config.get("inference_worker", {})
        if not inference_worker_cfg.get("enabled", False):
            logger.warning(
                "hailo_genai.llm_subprocess=True but inference_worker.enabled=False; "
                "auto-downgrading llm_subprocess to False"
            )
            hailo_genai_cfg["llm_subprocess"] = False
            return

        @app.before_serving
        async def start_inference_bridge() -> None:
            """Start the inference worker and bind event loop for LLM subprocess streaming."""
            import asyncio

            from core.inference_worker.bridge import inference_bridge
            from core.services_core.db_state import get_db_path

            db_path_str = str(get_db_path())
            inference_bridge.start(db_path_str, config)
            loop = asyncio.get_running_loop()
            inference_bridge.bind_event_loop(loop)
            logger.info("Inference worker started + event loop bound (llm_subprocess=True)")

        @app.after_serving
        async def stop_inference_bridge() -> None:
            """Stop the inference worker on shutdown."""
            from core.inference_worker.bridge import inference_bridge

            inference_bridge.stop(timeout=5.0)
            logger.info("Inference worker stopped")
