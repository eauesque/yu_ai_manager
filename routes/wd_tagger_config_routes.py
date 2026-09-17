"""Configuration routes for WD-Tagger."""

from quart import request

from core.infra_core.api_errors import api_error, api_result
from core.services_core.db_async import run_db_sync


class UnknownWdModelError(ValueError):
    pass


def register_config_routes(bp, wt_importer, require_admin_scope, logger):
    @bp.route("/api/wd-tagger/config", methods=["GET"])
    async def api_wt_config_get():
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err
        get_config = wt_importer("config_ops").get_config
        return api_result({"config": await run_db_sync(get_config)})

    @bp.route("/api/wd-tagger/config", methods=["POST"])
    async def api_wt_config_save():
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err
        data = await request.get_json(silent=True)
        if not isinstance(data, dict):
            return api_error("JSON object required", 400, code="invalid_json")
        try:
            save_config = wt_importer("config_ops").save_config
            saved = await run_db_sync(_save_config_and_sync_active, save_config, data)
            return api_result({"config": saved})
        except UnknownWdModelError:
            if logger is not None:
                logger.warning("Unknown WD-Tagger model in config save")
            return api_error(
                "Unknown WD model",
                400,
                code="unknown_model",
            )
        except ValueError:
            if logger is not None:
                logger.exception("Failed to save WD-Tagger config")
            return api_error(
                "Invalid WD-Tagger config",
                400,
                code="invalid_value",
            )


def _save_config_and_sync_active(save_config, data: dict):
    from core.configuration.json_rw import load_config_json, save_config_json
    from core.services_core import db_write, wd_active_model
    from core.services_core.db_state import get_db

    def _write():
        previous_config = load_config_json(None)
        con = get_db()
        try:
            model_id = None
            if "model" in data:
                model_id = wd_active_model.validate_model_id(data.get("model"))
                if model_id is not None and not _model_is_known_in_writer(
                    model_id,
                    con,
                ):
                    raise UnknownWdModelError(model_id)
            saved = save_config(data)
            if "model" in data:
                wd_active_model.set_active_wd_model_id_writer(model_id, con)
            con.commit()
            if "model" in data:
                from core.search_api.count_cache import count_cache

                count_cache.invalidate()
            return saved
        except Exception:
            con.rollback()
            save_config_json(previous_config)
            raise

    return db_write.submit_db_write(_write)


def _model_is_known_in_writer(model_id: str, con) -> bool:
    from core.services_core import wd_active_model
    from core.services_core.wd_dict_resolver import resolve_model_id_readonly

    if wd_active_model.model_is_builtin_profile(model_id):
        return True
    mid = resolve_model_id_readonly(con, model_id)
    if mid is None:
        return False
    row = con.execute(
        "SELECT 1 FROM file_wd_tags WHERE model_id = ? LIMIT 1",
        (mid,),
    ).fetchone()
    return row is not None
