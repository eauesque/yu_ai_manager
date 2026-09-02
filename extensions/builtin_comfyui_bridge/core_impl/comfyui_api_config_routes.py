"""Config routes for the ComfyUI bridge."""

from core.extensions_core.extensions_admin import (
    get_extension_config_value,
    save_extension_config_values,
)

from core.infra_core.api_errors import api_error, api_success
from core.infra_core.api_request import require_json_dict


def register_config_routes(
    bp,
    *,
    require_admin_scope,
    ext_name: str,
    save_naming_options,
    image_format_options,
    default_scheduler_options,
    default_sampler_options,
) -> None:
    @bp.route("/api/config", methods=["GET"])
    async def api_get_config():
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err
        return api_success({
            "api_url": get_extension_config_value(
                ext_name, "api_url", "http://127.0.0.1:8188"
            ),
            "auto_send": get_extension_config_value(ext_name, "auto_send", False),
            "default_sampler": get_extension_config_value(
                ext_name, "default_sampler", "euler"
            ),
            "default_scheduler": get_extension_config_value(
                ext_name, "default_scheduler", "normal"
            ),
            "save_folder": get_extension_config_value(ext_name, "save_folder", ""),
            "auto_save": get_extension_config_value(ext_name, "auto_save", False),
            "save_naming": get_extension_config_value(
                ext_name, "save_naming", "daily_folder"
            ),
            "auto_import": get_extension_config_value(ext_name, "auto_import", True),
            "default_image_format": get_extension_config_value(
                ext_name, "default_image_format", "png"
            ),
            "models_root": get_extension_config_value(ext_name, "models_root", ""),
            "bridge_managed_save": get_extension_config_value(
                ext_name, "bridge_managed_save", False
            ),
            "comfy_output_root": get_extension_config_value(
                ext_name, "comfy_output_root", ""
            ),
            # Default: True for new installs (= use save_folder), but False
            # for existing installs that already have a custom comfy_output_root
            # set, so we don't silently override their explicit path.
            "comfy_output_same_as_save_folder": get_extension_config_value(
                ext_name,
                "comfy_output_same_as_save_folder",
                not bool(
                    (get_extension_config_value(ext_name, "comfy_output_root", "") or "").strip()
                ),
            ),
            "max_batch_size": get_extension_config_value(ext_name, "max_batch_size", 8),
            "gateway_url": get_extension_config_value(ext_name, "gateway_url", ""),
            "api_key_enc": "***" if get_extension_config_value(ext_name, "api_key_enc", "") else "",
        })

    @bp.route("/api/config", methods=["POST"])
    async def api_save_config():
        from quart import request

        auth_err = require_admin_scope()
        if auth_err:
            return auth_err
        data, err = await require_json_dict(request)
        if err:
            return api_error(err[0]["error"], err[1])

        allowed = {
            "api_url", "auto_send", "default_sampler", "default_scheduler",
            "save_folder", "auto_save", "save_naming", "auto_import",
            "default_image_format", "models_root",
            "bridge_managed_save", "comfy_output_root",
            "comfy_output_same_as_save_folder",
            "max_batch_size", "api_key_enc", "gateway_url",
        }
        to_save = {k: v for k, v in data.items() if k in allowed}
        if not to_save:
            return api_error("No valid config fields provided", 400)

        url_val = to_save.get("api_url")
        if url_val is not None:
            url_str = str(url_val).strip()
            if not (url_str.startswith("http://") or url_str.startswith("https://")):
                return api_error("api_url must use http:// or https://", 400)
            to_save["api_url"] = url_str
        for bool_field in (
            "auto_send", "auto_save", "auto_import",
            "bridge_managed_save", "comfy_output_same_as_save_folder",
        ):
            if bool_field in to_save and not isinstance(to_save[bool_field], bool):
                return api_error(f"{bool_field} must be a boolean", 400)
        if "default_sampler" in to_save:
            sampler = str(to_save["default_sampler"]).strip()
            if not sampler:
                return api_error("default_sampler must not be empty", 400)
            if default_sampler_options and sampler not in default_sampler_options:
                return api_error("default_sampler is invalid", 400)
            to_save["default_sampler"] = sampler
        if "default_scheduler" in to_save:
            scheduler = str(to_save["default_scheduler"]).strip()
            if not scheduler:
                return api_error("default_scheduler must not be empty", 400)
            if default_scheduler_options and scheduler not in default_scheduler_options:
                return api_error("default_scheduler is invalid", 400)
            to_save["default_scheduler"] = scheduler
        if "save_folder" in to_save:
            if not isinstance(to_save["save_folder"], str):
                return api_error("save_folder must be a string", 400)
            to_save["save_folder"] = to_save["save_folder"].strip()
        if "models_root" in to_save:
            if not isinstance(to_save["models_root"], str):
                return api_error("models_root must be a string", 400)
            to_save["models_root"] = to_save["models_root"].strip()
        if "comfy_output_root" in to_save:
            if not isinstance(to_save["comfy_output_root"], str):
                return api_error("comfy_output_root must be a string", 400)
            to_save["comfy_output_root"] = to_save["comfy_output_root"].strip()
        if "save_naming" in to_save:
            naming = str(to_save["save_naming"]).strip()
            if naming not in save_naming_options:
                return api_error("save_naming is invalid", 400)
            to_save["save_naming"] = naming
        if "default_image_format" in to_save:
            image_format = str(to_save["default_image_format"]).strip().lower()
            if image_format not in image_format_options:
                return api_error("default_image_format is invalid", 400)
            to_save["default_image_format"] = image_format

        if "max_batch_size" in to_save:
            try:
                mbs = int(to_save["max_batch_size"])
            except (TypeError, ValueError):
                return api_error("max_batch_size must be an integer", 400)
            if mbs < 1 or mbs > 64:
                return api_error("max_batch_size must be between 1 and 64", 400)
            to_save["max_batch_size"] = mbs

        if "gateway_url" in to_save:
            gw_val = str(to_save.get("gateway_url") or "").strip()
            if gw_val:
                from core.gateway.bridge_validation import validate_comfy_gateway_url
                err = validate_comfy_gateway_url(gw_val)
                if err:
                    return api_error(f"gateway_url invalid: {err}", 400)
            to_save["gateway_url"] = gw_val

        if "api_key_enc" in to_save:
            raw = str(to_save.get("api_key_enc") or "").strip()
            # Skip the masked sentinel "***" that the GET endpoint returns —
            # round-tripping it would overwrite the real key with encrypt("***").
            if raw == "***":
                del to_save["api_key_enc"]
            elif raw and not raw.startswith("enc:"):
                from core.settings_core.secret_store import encrypt
                to_save["api_key_enc"] = encrypt(raw)
            # else: empty (clears key) or already enc: — pass through as-is

        save_extension_config_values(ext_name, to_save)
        # Redact api_key_enc from the response to avoid echoing ciphertext.
        resp_saved = {
            k: ("***" if k == "api_key_enc" and v else v)
            for k, v in to_save.items()
        }
        return api_success({"saved": resp_saved})
