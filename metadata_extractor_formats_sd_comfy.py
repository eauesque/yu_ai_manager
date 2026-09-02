"""Stable Diffusion / ComfyUI metadata helpers (compat facade)."""

from core.tools.metadata.formats_sd_comfy import extract_comfyui, extract_sd

__all__ = ["extract_sd", "extract_comfyui"]
