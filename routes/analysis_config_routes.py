from quart import request

from core.analysis_api.config_ops import get_analysis_config, save_analysis_config
from core.infra_core.api_errors import api_error, api_result
from core.infra_core.api_request import require_json_dict
from core.services_core.db_async import run_db_sync
from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def register_analysis_config_routes(bp):
    @bp.route("/api/analysis/config", methods=["GET", "POST"])
    async def api_analysis_config():
        if request.method == "GET":
            auth_err = _require_admin_scope()
            if auth_err:
                return auth_err
            return api_result(await run_db_sync(get_analysis_config), 200)
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data, err = await require_json_dict(request)
        if err:
            return api_result(err[0], err[1])
        payload, status = await run_db_sync(save_analysis_config, data)
        return api_result(payload, status)

    @bp.route("/api/analysis/available-engines")
    async def api_available_engines():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        try:
            from core.analysis_api.config_ops import get_available_engines

            engines = await run_db_sync(get_available_engines)
            return api_result({"engines": engines}, 200)
        except Exception:
            return api_error("Failed to get available engines", 500)

    @bp.route("/api/analysis/ollama/models")
    async def api_ollama_models():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.analysis.ollama_utils import check_ollama_connection, validate_ollama_url
        from core.configuration.api import load_config_json

        config = load_config_json(None)
        base_url = config.get("ai_analysis", {}).get("ollama_url", "http://localhost:11434")
        err = validate_ollama_url(base_url)
        if err:
            return api_error(err, 400)
        result = await run_db_sync(check_ollama_connection, base_url)
        return api_result(result, 200)

    @bp.route("/api/analysis/ollama/test", methods=["POST"])
    async def api_ollama_test():
        from core.analysis.ollama_utils import check_ollama_connection, validate_ollama_url

        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data, err = await require_json_dict(request)
        if err:
            return api_result(err[0], err[1])
        base_url = (data.get("ollama_url") or "").strip()
        if not base_url:
            return api_error("URL is required", 400)
        url_err = validate_ollama_url(base_url)
        if url_err:
            return api_error(url_err, 400)
        result = await run_db_sync(check_ollama_connection, base_url)
        return api_result(result, 200)

    @bp.route("/api/analysis/openai-compat/models")
    async def api_openai_compat_models():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.analysis.openai_compat_utils import check_openai_compat_connection, validate_openai_compat_url
        from core.configuration.api import load_config_json
        from core.settings_core.secret_store import decrypt

        config = load_config_json(None)
        ai = config.get("ai_analysis", {})
        base_url = ai.get("openai_compat_url", "")
        if not base_url:
            return api_error("OpenAI Compatible URL is not configured", 400)
        err = validate_openai_compat_url(base_url, allow_local=True)
        if err:
            return api_error(err, 400)
        api_key = decrypt(ai.get("openai_compat_api_key", ""))
        result = await run_db_sync(check_openai_compat_connection, base_url, api_key, allow_local=True)
        return api_result(result, 200)

    @bp.route("/api/analysis/openai-compat/test", methods=["POST"])
    async def api_openai_compat_test():
        from core.analysis.openai_compat_utils import check_openai_compat_connection, validate_openai_compat_url

        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data, err = await require_json_dict(request)
        if err:
            return api_result(err[0], err[1])
        base_url = (data.get("url") or "").strip()
        if not base_url:
            return api_error("URL is required", 400)
        url_err = validate_openai_compat_url(base_url, allow_local=True)
        if url_err:
            return api_error(url_err, 400)
        api_key = (data.get("api_key") or "").strip()
        result = await run_db_sync(check_openai_compat_connection, base_url, api_key, allow_local=True)
        return api_result(result, 200)
