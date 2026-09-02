"""Info and progress routes for the ComfyUI bridge."""

from quart import jsonify, render_template, request

from core.infra_core.api_errors import api_error, api_success


def register_info_routes(
    bp,
    *,
    make_client,
    get_api_url,
    progress_state,
    ext_name: str,
    bridge_tag: str,
) -> None:
    @bp.route("/")
    async def bridge_ui():
        return await render_template("comfyui_bridge.html")

    @bp.route("/info")
    async def bridge_info():
        return jsonify({
            "name": ext_name,
            "bridge": bridge_tag,
            "api_url": get_api_url(),
        })

    @bp.route("/api/test-connection", methods=["POST"])
    async def api_test_connection():
        client = make_client()
        result = client.test_connection()
        if result["ok"]:
            return api_success(result)
        return api_error(result.get("error", "Connection failed"), 502)

    @bp.route("/api/samplers")
    async def api_samplers():
        client = make_client()
        samplers = client.list_samplers()
        return api_success({"samplers": samplers})

    @bp.route("/api/schedulers")
    async def api_schedulers():
        client = make_client()
        schedulers = client.list_schedulers()
        return api_success({"schedulers": schedulers})

    @bp.route("/api/models")
    async def api_models():
        client = make_client()
        models = client.list_models()
        return api_success({"models": models})

    @bp.route("/api/refresh-assets", methods=["POST"])
    async def api_refresh_assets():
        """Re-query ComfyUI's loader nodes so its mtime-based file cache
        rebuilds and picks up newly-added checkpoints / LoRAs / VAEs."""
        try:
            client = make_client()
        except Exception as exc:  # noqa: BLE001
            return api_error(f"ComfyUI connection failed: {exc}", 502)
        try:
            results = client.refresh_assets()
        except Exception as exc:  # noqa: BLE001
            return api_error(f"refresh failed: {exc}", 500)
        return api_success({"results": results})

    @bp.route("/api/has-node")
    async def api_has_node():
        from quart import request
        node_type = request.args.get("type", "")
        if not node_type:
            return api_error("missing 'type' query param", 400)
        client = make_client()
        return api_success({"node_type": node_type, "available": client.has_node(node_type)})

    @bp.route("/api/progress")
    async def api_progress():
        from core.bridge_core.task_registry import get_progress_dict
        task_id = request.args.get("task_id") or None
        return api_success(get_progress_dict(task_id))

    @bp.route("/api/cancel", methods=["POST"])
    async def api_cancel():
        from core.bridge_core.bridge_handlers import get_cancel
        data = await request.get_json(silent=True) or {}
        task_id = data.get("task_id") or None
        if task_id:
            from core.bridge_core import task_registry as _tr
            ok = _tr.cancel_task(task_id)
            if not ok:
                return api_error("task not found", 404)
            return api_success({"cancelled": True})
        handler = get_cancel(bridge_tag)
        if handler is None:
            return api_error(
                f"cancel handler not registered for {bridge_tag}", 503,
            )
        return await handler({})
