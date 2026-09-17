"""Extension API config operations."""

from .extensions_admin import (
    get_extension_config_value,
    save_extension_config_values,
    validate_config_value,
)

_SECRET_FIELD_TOKENS = ("secret", "token", "password", "api_key", "apikey")


def _is_secret_field(field_name: str) -> bool:
    lowered = str(field_name or "").strip().lower()
    return any(token in lowered for token in _SECRET_FIELD_TOKENS)


def build_config_schema(manifest, ext_name: str):
    schema = {}
    for field_name, cf in manifest.config_schema.items():
        value = get_extension_config_value(ext_name, field_name, cf.default)
        if _is_secret_field(field_name):
            value = None
        schema[field_name] = {
            "type": cf.type,
            "default": cf.default,
            "label": cf.label,
            "cli_flag": cf.cli_flag,
            "options": cf.options,
            "range": cf.range,
            "description": cf.description,
            "value": value,
        }
    return schema


def validate_and_save_config(manifest, ext_name: str, values: dict):
    errors = []
    for field_name, value in values.items():
        cf = manifest.config_schema.get(field_name)
        if cf is None:
            errors.append(f"Unknown config field: {field_name}")
            continue
        err = validate_config_value(cf, value)
        if err:
            errors.append(f"{field_name}: {err}")
    if errors:
        return {"error": "Validation failed", "details": errors}, 400
    save_extension_config_values(ext_name, values)
    return {"name": ext_name, "saved": values}, 200
