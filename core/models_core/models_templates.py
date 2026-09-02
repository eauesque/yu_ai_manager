"""DB CRUD for templates and template_tokens tables (compat facade)."""

from .models_template_model_info import extract_comfyui_model, extract_model_info
from .models_template_write import replace_template_tokens, upsert_template

__all__ = [
    "extract_comfyui_model",
    "extract_model_info",
    "replace_template_tokens",
    "upsert_template",
]
