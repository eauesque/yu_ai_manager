"""Hailo-10H GenAI extension entry point (LLM / VLM / Speech2Text)."""

import asyncio
import logging
import os
import sys
from pathlib import Path

_ext_dir = Path(__file__).resolve().parent
_project_root = _ext_dir.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
if str(_ext_dir) not in sys.path:
    sys.path.insert(0, str(_ext_dir))

from core.extensions_core.extensions_admin import get_extension_config_value
from quart import Blueprint, jsonify, render_template, request

_EXT_NAME = "builtin-hailo-genai"


def get_health() -> dict:
    """Unified health probe — consumed by /api/extensions.

    Reports the default LLM HEF as the representative HEF (the most common
    path; other GenAI HEFs are downloaded on demand and not gating
    availability of the extension as a whole).
    """
    from core.hailo_device_core.hailo_health import build_health

    from .core_impl.model_download import _DEFAULT_HEF_DIR, GENAI_MODELS, is_hef_available
    default_model = get_extension_config_value(
        _EXT_NAME, "default_llm_model", "qwen3-1.7b-instruct",
    )
    if default_model in GENAI_MODELS:
        hef_ok = is_hef_available(default_model)
        hint = f"{default_model} under {_DEFAULT_HEF_DIR}"
    else:
        # Fall back to "any GenAI HEF present"
        hef_dir = Path(_DEFAULT_HEF_DIR)
        hef_ok = hef_dir.is_dir() and any(hef_dir.rglob("*.hef"))
        hint = str(hef_dir)
    return build_health(hef_ok=hef_ok, hef_label="GenAI model", hef_hint=hint)


from core.web.auth_helpers import require_admin_scope as _require_admin_scope

logger = logging.getLogger(__name__)


def _get_runtime_payload() -> dict:
    """Build non-health runtime data for the tools UI."""
    from core.hailo_device_core.device_manager import get_active_owners

    from .core_impl.model_download import get_model_status

    active = get_active_owners()

    context_info = None
    for owner in active:
        if owner in ("llm", "vlm"):
            try:
                if owner == "llm":
                    from .core_impl.llm_inference import _instance
                    if _instance:
                        context_info = _instance.get_context_info()
                elif owner == "vlm":
                    from .core_impl.vlm_inference import _instance
                    if _instance:
                        context_info = _instance.get_context_info()
            except Exception:
                logger.debug("no engine loaded; no context to report", exc_info=True)

    return {
        "status": "ok",
        "models": get_model_status(),
        "context": context_info,
    }


def _public_error_detail(exc: Exception) -> str:
    """Return a one-line error detail without local absolute paths."""
    detail = f"{type(exc).__name__}: {exc}".replace("\r", " ").replace("\n", " ")
    cwd = os.path.realpath(os.getcwd())
    detail = detail.replace(cwd, "<app>")
    return " ".join(detail.split())


def get_blueprint():
    """Return the Quart Blueprint for Hailo GenAI."""
    # The model registry is built from cache/bundled rows at import so that no
    # request ever waits on the network. Kick the remote refresh off here, at
    # registration, on its own thread: a server process gets fresh model rows
    # within seconds, and a host without DNS just keeps the local ones.
    try:
        from .core_impl.model_download import start_remote_registry_refresh

        start_remote_registry_refresh()
    except ImportError:  # pragma: no cover - extension imported without core_impl
        pass

    bp = Blueprint(
        "ext_hailo_genai",
        __name__,
        template_folder="templates",
    )

    # ── Index page ───────────────────────────────────────────────

    @bp.route("/")
    async def index():
        return await render_template("hailo_genai/genai.html")

    @bp.route("/chat")
    async def chat_page():
        return await render_template("hailo_genai/chat.html")

    @bp.route("/api/runtime")
    async def api_runtime():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        return jsonify(_get_runtime_payload())

    # ── System diagnostics ──────────────────────────────────────

    @bp.route("/api/system/cma")
    async def api_system_cma():
        """Return a CMA telemetry snapshot for diagnostics.

        Authentication: same admin scope as other GenAI endpoints. The data
        itself is benign system info (CmaFree from /proc/meminfo + names of
        currently active Hailo model owners), but we keep the gate for
        consistency.

        Response shape:
            {"status": "ok",
             "cma": {"free_mb": int|null, "total_mb": int|null,
                     "active_hailo_models": [str, ...]}}
        """
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.hailo_device_core.auto_reboot import get_judge
        from core.hailo_device_core.device_helpers import (
            _read_cma_free_mb,
            _read_cma_total_mb,
        )
        from core.hailo_device_core.device_manager_state import get_active_owners
        judge = get_judge()
        auto_reboot = judge.snapshot() if judge else {
            "enabled": False,
            "mode": "off",
            "dry_run": False,
            "state": "idle",
            "would_fire_count": 0,
            "consecutive_rejects": 0,
            "hailo_runtime_version": None,
        }
        return jsonify({
            "status": "ok",
            "cma": {
                "free_mb": _read_cma_free_mb(),
                "total_mb": _read_cma_total_mb(),
                "active_hailo_models": get_active_owners(),
                "auto_reboot": auto_reboot,
            },
        })

    # ── Model management ────────────────────────────────────────

    @bp.route("/api/model/status")
    async def api_model_status():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from .core_impl.model_download import get_model_status
        return jsonify({"status": "ok", "models": get_model_status()})

    @bp.route("/api/model/download", methods=["POST"])
    async def api_model_download():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from .core_impl.model_download import (
            GENAI_MODELS,
            download_hef,
        )

        data = await request.get_json(silent=True) or {}
        model_name = data.get("model", "")

        if model_name not in GENAI_MODELS:
            return jsonify({
                "status": "error",
                "message": f"Unknown model: {model_name}",
                "available": list(GENAI_MODELS.keys()),
            }), 400

        try:
            await asyncio.to_thread(download_hef, model_name)
            return jsonify({
                "status": "ok",
                "model": model_name,
            })
        except Exception as exc:
            import logging as _lg
            _lg.getLogger(__name__).error("Model download failed for %s: %s", model_name, exc)
            return jsonify({
                "status": "error",
                "message": f"Model download failed: {_public_error_detail(exc)}",
            }), 500

    @bp.route("/api/model/unload", methods=["POST"])
    async def api_model_unload():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.configuration.api import load_config_json

        from .core_impl.llm_control import async_status, async_unload_model

        config = load_config_json(None)
        data = await request.get_json(silent=True) or {}
        target = data.get("model")  # "llm", "vlm", "s2t", or None=all

        status = await async_status(config, force=True)
        candidates = ["llm", "vlm", "s2t"]
        unloaded = []
        for owner in candidates:
            if target and target != owner:
                continue
            if status.get(f"{owner}_active"):
                try:
                    await async_unload_model(owner, config)
                    unloaded.append(owner)
                except Exception as exc:
                    import logging as _lg
                    _lg.getLogger(__name__).warning("Unload %s failed: %s", owner, exc)

        if not unloaded:
            return jsonify({
                "status": "error",
                "message": "No GenAI model is currently loaded",
            }), 400

        return jsonify({"status": "ok", "unloaded": unloaded})

    # ── Register sub-routes ─────────────────────────────────────
    from hailo_chat_routes import register_chat_routes
    from hailo_llm_routes import register_llm_routes
    from hailo_s2t_routes import register_s2t_routes
    from hailo_vlm_routes import register_vlm_routes

    register_llm_routes(bp)
    register_vlm_routes(bp)
    register_s2t_routes(bp)
    register_chat_routes(bp)

    from hailo_openai_routes import register_openai_routes
    register_openai_routes(bp)

    return bp


__all__ = ["get_blueprint", "get_health"]
