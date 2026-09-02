"""Profile CRUD API routes."""

import logging

from quart import current_app, request

from core.configuration.profiles import (
    create_profile,
    delete_profile,
    duplicate_profile,
    list_profiles,
    load_profile,
    rename_profile,
    update_profile_metadata,
    validate_profile_name,
)
from core.infra_core.api_errors import api_error, api_result, api_success
from core.infra_core.api_request import require_json_model
from core.profiles_api.request_models import (
    ProfileCreateRequest,
    ProfileDuplicateRequest,
    ProfileRenameRequest,
    ProfileUpdateRequest,
)
from core.services_core.db_async import run_db_sync
from core.web.auth_helpers import require_admin_scope as _require_admin_scope
from core.web.auth_helpers import require_pin as _require_pin

logger = logging.getLogger(__name__)


def register_profiles_crud_routes(bp):
    """Register profile CRUD endpoints on *bp*."""

    @bp.route("/api/profiles", methods=["GET"])
    async def api_profiles_list():
        auth_err = _require_pin()
        if auth_err:
            return auth_err
        scope_err = _require_admin_scope()
        if scope_err:
            return scope_err
        active = current_app.config.get("ACTIVE_PROFILE")

        def _list():
            profiles = list_profiles()
            for p in profiles:
                p["is_active"] = p["name"] == active
            return profiles

        profiles = await run_db_sync(_list)
        return api_success({"profiles": profiles})

    @bp.route("/api/profiles/<name>", methods=["GET"])
    async def api_profiles_detail(name: str):
        auth_err = _require_pin()
        if auth_err:
            return auth_err
        scope_err = _require_admin_scope()
        if scope_err:
            return scope_err
        err = validate_profile_name(name)
        if err:
            return api_error(err, 400, code="invalid_profile_name")
        active = current_app.config.get("ACTIVE_PROFILE")
        data = await run_db_sync(load_profile, name)
        if data is None:
            return api_error(f"Profile '{name}' not found", 404, code="profile_not_found")
        data["is_active"] = name == active
        return api_success({"profile": data})

    @bp.route("/api/profiles", methods=["POST"])
    async def api_profiles_create():
        auth_err = _require_pin()
        if auth_err:
            return auth_err
        data, err = await require_json_model(request, ProfileCreateRequest)
        if err:
            return api_result(err[0], err[1])

        assert data is not None
        name = data.name
        label = (data.label or name).strip()
        description = data.description.strip()
        base_config = data.base_config

        name_err = validate_profile_name(name)
        if name_err:
            return api_error(name_err, 400, code="invalid_profile_name")
        if not label:
            return api_error("Label must not be empty", 400, code="invalid_label")

        try:
            profile = await run_db_sync(create_profile, name, label, description, base_config)
        except ValueError as exc:
            logger.warning("Profile create failed for %s: %s", name, exc)
            return api_error("Profile already exists or could not be created", 409, code="profile_exists")
        return api_success({"profile": profile}, 201)

    @bp.route("/api/profiles/<name>", methods=["PUT"])
    async def api_profiles_update(name: str):
        auth_err = _require_pin()
        if auth_err:
            return auth_err
        data, err = await require_json_model(request, ProfileUpdateRequest)
        if err:
            return api_result(err[0], err[1])

        kwargs = {}
        assert data is not None
        fields_set = data.model_fields_set
        if "label" in fields_set:
            kwargs["label"] = (data.label or "").strip()
        if "description" in fields_set:
            kwargs["description"] = (data.description or "").strip()
        if "favorite" in fields_set:
            kwargs["favorite"] = data.favorite
        if not kwargs:
            return api_error("No fields to update", 400, code="empty_update")

        try:
            profile = await run_db_sync(update_profile_metadata, name, **kwargs)
        except ValueError as exc:
            logger.warning("Profile update failed for %s: %s", name, exc)
            return api_error("Profile update failed", 400, code="update_failed")
        return api_success({"profile": profile})

    @bp.route("/api/profiles/<name>", methods=["DELETE"])
    async def api_profiles_delete(name: str):
        auth_err = _require_pin()
        if auth_err:
            return auth_err
        if name == current_app.config.get("ACTIVE_PROFILE"):
            return api_error("Cannot delete the active profile", 400, code="delete_active")

        try:
            await run_db_sync(delete_profile, name)
        except ValueError as exc:
            logger.warning("Profile delete failed for %s: %s", name, exc)
            return api_error("Profile delete failed", 400, code="delete_failed")
        return api_success({"deleted": name})

    @bp.route("/api/profiles/<name>/duplicate", methods=["POST"])
    async def api_profiles_duplicate(name: str):
        auth_err = _require_pin()
        if auth_err:
            return auth_err
        data, err = await require_json_model(request, ProfileDuplicateRequest)
        if err:
            return api_result(err[0], err[1])

        assert data is not None
        new_name = data.new_name
        new_label = (data.new_label or new_name).strip()

        try:
            profile = await run_db_sync(duplicate_profile, name, new_name, new_label)
        except ValueError as exc:
            logger.warning("Profile duplicate failed from %s to %s: %s", name, new_name, exc)
            return api_error("Profile duplication failed", 400, code="duplicate_failed")
        return api_success({"profile": profile}, 201)

    @bp.route("/api/profiles/<name>/rename", methods=["POST"])
    async def api_profiles_rename(name: str):
        auth_err = _require_pin()
        if auth_err:
            return auth_err
        data, err = await require_json_model(request, ProfileRenameRequest)
        if err:
            return api_result(err[0], err[1])

        assert data is not None
        new_name = data.new_name
        name_err = validate_profile_name(new_name)
        if name_err:
            return api_error(name_err, 400, code="invalid_profile_name")

        # If renaming the active profile, update config.json
        is_active = name == current_app.config.get("ACTIVE_PROFILE")

        try:
            profile = await run_db_sync(rename_profile, name, new_name)
        except ValueError as exc:
            logger.warning("Profile rename failed from %s to %s: %s", name, new_name, exc)
            return api_error("Profile rename failed", 400, code="rename_failed")

        if is_active:
            def _update_config():
                from core.configuration.json_rw import load_config_json, save_config_json
                cfg = load_config_json(None)
                cfg["active_profile"] = new_name
                save_config_json(cfg)

            await run_db_sync(_update_config)
            current_app.config["ACTIVE_PROFILE"] = new_name

        return api_success({"profile": profile})

    @bp.route("/api/profiles/<name>/favorite", methods=["POST"])
    async def api_profiles_favorite(name: str):
        auth_err = _require_pin()
        if auth_err:
            return auth_err
        data = await run_db_sync(load_profile, name)
        if data is None:
            return api_error(f"Profile '{name}' not found", 404, code="profile_not_found")

        new_fav = not data.get("favorite", False)
        try:
            profile = await run_db_sync(update_profile_metadata, name, favorite=new_fav)
        except ValueError as exc:
            logger.warning("Profile favorite toggle failed for %s: %s", name, exc)
            return api_error("Profile favorite update failed", 400, code="favorite_failed")
        return api_success({"profile": profile})
