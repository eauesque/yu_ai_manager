"""ComfyUI CLIP extraction compatibility facade."""

from .comfyui_extract_clip_params import extract_ksampler_params
from .comfyui_extract_clip_texts import find_clip_texts

__all__ = ["extract_ksampler_params", "find_clip_texts"]
