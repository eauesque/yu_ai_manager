"""Info, connection, and progress routes for the SD WebUI bridge."""

from quart import jsonify, render_template, request

from core.infra_core.api_errors import api_error, api_success


def register_info_routes(
    bp,
    *,
    make_client,
    get_api_url,
    reset_client_cache,
    ext_name: str,
    bridge_tag: str,
    logger,
) -> None:
    @bp.route("/")
    async def bridge_ui():
        return await render_template("sd_webui_bridge.html")

    @bp.route("/info")
    async def bridge_info():
        return jsonify({
            "name": ext_name,
            "bridge": bridge_tag,
            "api_url": get_api_url(),
        })

    @bp.route("/api/test-connection", methods=["POST"])
    async def api_test_connection():
        reset_client_cache()
        try:
            client = make_client()
        except Exception as exc:
            logger.warning(
                "SD WebUI test connection failed during client init: %s",
                exc,
            )
            return api_error("SD WebUI connection failed", 502)
        result = client.test_connection()
        if result["ok"]:
            result["api_type"] = getattr(client, "api_type", "sdapi_v1")
            return api_success(result)
        return api_error(result.get("error", "Connection failed"), 502)

    @bp.route("/api/samplers")
    async def api_samplers():
        try:
            client = make_client()
        except Exception as exc:
            logger.warning("SD WebUI samplers client init failed: %s", exc)
            return api_error("SD WebUI connection failed", 502)
        samplers = client.list_samplers()
        return api_success({"samplers": samplers})

    @bp.route("/api/upscalers")
    async def api_upscalers():
        try:
            client = make_client()
        except Exception as exc:
            logger.warning("SD WebUI upscalers client init failed: %s", exc)
            return api_error("SD WebUI connection failed", 502)
        upscalers = client.list_upscalers()
        return api_success({"upscalers": upscalers})

    @bp.route("/api/progress")
    async def api_progress():
        from core.bridge_core.task_registry import get_progress_dict
        task_id = request.args.get("task_id") or None
        if task_id:
            return api_success(get_progress_dict(task_id))
        # No task_id: poll SD WebUI backend directly (legacy non-fanout path)
        try:
            client = make_client()
            prog = client.get_progress()
        except Exception:
            return api_success({"progress": 0, "step": 0, "total_steps": 0, "eta_relative": 0})
        step = prog.get("state", {}).get("sampling_step", 0)
        total = prog.get("state", {}).get("sampling_steps", 0)
        return api_success({
            "progress": prog.get("progress", 0),
            "step": step,
            "total_steps": total,
            "eta_relative": prog.get("eta_relative", 0),
        })

    @bp.route("/api/cancel", methods=["POST"])
    async def api_cancel():
        from core.bridge_core.bridge_handlers import get_cancel
        data = await request.get_json(silent=True) or {}
        task_id = data.get("task_id") or None
        if task_id:
            from core.bridge_core import task_registry as _tr
            task = _tr.get_task_entry(task_id)
            if task is None:
                return api_error("task not found", 404)
            ok = _tr.cancel_task(task_id)
            if not ok:
                return api_success({"cancelled": False, "message": "task not yet cancellable"})
            return api_success({"cancelled": True})
        handler = get_cancel(bridge_tag)
        assert handler is not None, f"cancel handler not registered for {bridge_tag}"
        return await handler({})
