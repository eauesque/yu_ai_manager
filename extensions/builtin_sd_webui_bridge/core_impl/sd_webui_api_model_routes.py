"""Model-related routes for the SD WebUI bridge."""

from core.infra_core.api_errors import api_error, api_success
from core.infra_core.api_request import require_json_dict


def register_model_routes(bp, *, make_client, logger) -> None:
    @bp.route("/api/models")
    async def api_models():
        try:
            client = make_client()
        except Exception as exc:
            logger.warning("SD WebUI models client init failed: %s", exc)
            return api_error("SD WebUI connection failed", 502)
        models = client.list_models()
        return api_success({"models": models})

    @bp.route("/api/models/switch", methods=["POST"])
    async def api_switch_model():
        from quart import request

        data, err = await require_json_dict(request)
        if err:
            return api_error(err[0]["error"], err[1])
        checkpoint = (data.get("model") or "").strip()
        if not checkpoint:
            return api_error("model is required", 400)
        try:
            client = make_client()
        except Exception as exc:
            logger.warning("SD WebUI switch model client init failed: %s", exc)
            return api_error("SD WebUI connection failed", 502)
        try:
            result = client.switch_model(checkpoint)
        except Exception as exc:
            logger.exception("SD WebUI switch model failed: %s", exc)
            return api_error(f"Switch failed: {exc}", 500)
        if result["ok"]:
            return api_success(result)
        return api_error(result.get("error", "Switch failed"), 502)

    @bp.route("/api/refresh-assets", methods=["POST"])
    async def api_refresh_assets():
        """Ask SD WebUI to rescan checkpoints / VAE / LoRAs on disk."""
        try:
            client = make_client()
        except Exception as exc:
            logger.warning("SD WebUI refresh-assets client init failed: %s", exc)
            return api_error("SD WebUI connection failed", 502)
        try:
            results = client.refresh_assets()
        except Exception as exc:
            logger.exception("SD WebUI refresh-assets failed: %s", exc)
            return api_error(f"refresh failed: {exc}", 500)
        return api_success({"results": results})
