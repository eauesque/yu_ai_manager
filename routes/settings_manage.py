"""Settings Management API — schema retrieval, settings CRUD.

GET endpoints have no rate limit.
PUT uses the DESTRUCTIVE rate-limit tier.

Vault integration (1Password / Bitwarden) and secret management routes
are registered from sub-modules.
"""

from typing import Any

from pydantic import StrictStr, TypeAdapter, ValidationError
from quart import Blueprint, request

from core.infra_core.api_errors import api_error, api_result
from core.infra_core.api_models import ApiModel
from core.infra_core.api_request import require_json_model
from core.services_core.db_async import run_db_sync
from routes.settings_manage_secrets import register_secrets_routes
from routes.settings_manage_vault_bw import register_vault_bw_routes
from routes.settings_manage_vault_op import register_vault_op_routes

bp = Blueprint("settings_manage", __name__)

# Register sub-module routes on this blueprint
register_vault_op_routes(bp)
register_vault_bw_routes(bp)
register_secrets_routes(bp)


class SettingValueRequest(ApiModel):
    value: Any
    op_uri: StrictStr | None = None


from core.web.auth_helpers import require_admin_scope as _require_admin_scope

# -- Schema ----------------------------------------------------------------

@bp.route("/api/settings/schema")
async def api_settings_schema():
    """Return the full settings schema."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    from core.settings_core.settings_schema import get_schema
    return api_result({"schema": await run_db_sync(get_schema)}, 200)


# -- Read all --------------------------------------------------------------

@bp.route("/api/settings/all")
async def api_settings_all():
    """Return all setting values (secrets are masked)."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    def _fetch_all():
        from core.configuration.json_rw import load_config_json
        from core.settings_core import bw_store, op_store
        from core.settings_core.secret_store import decrypt, is_encrypted, mask_secret
        from core.settings_core.settings_schema import (
            SETTINGS_SCHEMA,
            resolve_dotted_key,
        )

        config = load_config_json()
        op_map = config.get("op_secrets", {}) if isinstance(config.get("op_secrets"), dict) else {}
        bw_map = config.get("bw_secrets", {}) if isinstance(config.get("bw_secrets"), dict) else {}
        result = []

        for s in SETTINGS_SCHEMA:
            raw = resolve_dotted_key(config, s.key)

            # Determine source: 1Password / Bitwarden / encrypted / config / default
            # For external vaults, check the mapping without invoking the CLI —
            # calling op/bw on every key triggers repeated auth prompts on Windows.
            source = "default"
            if s.key in op_map:
                source = "1password"
                display = "****" if s.secret else op_store.resolve_secret(s.key, config)
            elif s.key in bw_map:
                source = "bitwarden"
                display = "****" if s.secret else bw_store.resolve_secret(s.key, config)

            if source == "default" and raw is not None:
                if s.secret and is_encrypted(str(raw)):
                    source = "encrypted"
                    display = mask_secret(decrypt(str(raw)))
                elif s.secret:
                    source = "config"
                    display = mask_secret(str(raw))
                else:
                    source = "config"
                    display = raw
            elif source == "default":
                display = s.default
                # Auto-detect system timezone when not configured
                if s.key == "timezone" and display is None:
                    from core.timezone_core.tz_helper import detect_system_timezone  # noqa: PLC0415
                    display = detect_system_timezone()
                    source = "system"

            result.append({
                "key": s.key,
                "value": display,
                "source": source,
                "secret": s.secret,
                "category": s.category,
            })

        return result

    settings = await run_db_sync(_fetch_all)
    return api_result({"settings": settings}, 200)


# -- Read single -----------------------------------------------------------

@bp.route("/api/settings/<path:key>")
async def api_settings_get(key: str):
    """Return a single setting value (secrets are masked)."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    def _fetch_single(k):
        from core.configuration.json_rw import load_config_json
        from core.settings_core import bw_store, op_store
        from core.settings_core.secret_store import decrypt, is_encrypted, mask_secret
        from core.settings_core.settings_schema import get_schema_def, resolve_dotted_key

        schema_def = get_schema_def(k)
        if schema_def is None:
            return None

        config = load_config_json()
        raw = resolve_dotted_key(config, k)

        source = "default"
        display = schema_def.default

        op_val = op_store.resolve_secret(k, config)
        if op_val is not None:
            source = "1password"
            display = mask_secret(op_val) if schema_def.secret else op_val
        else:
            bw_val = bw_store.resolve_secret(k, config)
            if bw_val is not None:
                source = "bitwarden"
                display = mask_secret(bw_val) if schema_def.secret else bw_val

        if source == "default" and raw is not None:
            if schema_def.secret and is_encrypted(str(raw)):
                source = "encrypted"
                display = mask_secret(decrypt(str(raw)))
            elif schema_def.secret:
                source = "config"
                display = mask_secret(str(raw))
            else:
                source = "config"
                display = raw

        return {
            "key": k,
            "value": display,
            "source": source,
            "secret": schema_def.secret,
            "category": schema_def.category,
        }

    result = await run_db_sync(_fetch_single, key)
    if result is None:
        return api_error("Unknown setting key", 404, code="not_found")
    return api_result(result, 200)


# -- Write single ----------------------------------------------------------

@bp.route("/api/settings/<path:key>", methods=["PUT"])
async def api_settings_put(key: str):
    """Update a setting value. Secrets are auto-encrypted. Supports op_uri."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err

    from core.settings_core.settings_schema import get_schema_def

    schema_def = get_schema_def(key)
    if schema_def is None:
        return api_error("Unknown setting key", 404, code="not_found")

    body, err = await require_json_model(request, SettingValueRequest)
    if err:
        return api_error(err[0]["error"], err[1], code=err[0].get("code", "validation_error"))

    assert body is not None
    value = body.value
    op_uri = body.op_uri  # Optional: 1Password URI setting

    # Type coercion
    try:
        value = _coerce_value(value, schema_def.type)
    except ValueError as exc:
        return api_error(str(exc), 400, code="bad_request")

    def _save(k, val, uri, is_secret):
        from core.configuration.json_rw import load_config_json, save_config_json
        from core.settings_core.secret_store import encrypt
        from core.settings_core.settings_schema import set_dotted_key

        config = load_config_json()
        if uri:
            op_map = config.setdefault("op_secrets", {})
            op_map[k] = uri
        else:
            if is_secret and isinstance(val, str) and val:
                val = encrypt(val)
            set_dotted_key(config, k, val)
        save_config_json(config)

    await run_db_sync(_save, key, value, op_uri, schema_def.secret)

    return api_result({"key": key, "updated": True}, 200)


# -- Helpers ---------------------------------------------------------------

def _coerce_value(value, type_name: str):
    """Coerce a value to the type specified in the schema."""
    if value is None:
        return None
    adapter = {
        "bool": TypeAdapter(bool),
        "int": TypeAdapter(int),
        "float": TypeAdapter(float),
        "str": TypeAdapter(str),
    }.get(type_name)
    if adapter is None:
        return value
    try:
        return adapter.validate_python(value, strict=True)
    except ValidationError as exc:
        messages = {
            "bool": "value must be a boolean",
            "int": "value must be an integer",
            "float": "value must be a number",
            "str": "value must be a string",
        }
        raise ValueError(messages[type_name]) from exc
    return value
