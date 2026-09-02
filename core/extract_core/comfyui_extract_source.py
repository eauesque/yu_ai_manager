"""ComfyUI source inference helpers."""

from pathlib import Path


def infer_comfy_meta_source(filepath: str) -> str:
    from core.helpers_core.helpers_text_path import archive_part
    suf = Path(archive_part(filepath) if "!" in filepath else filepath).suffix.lower()
    if suf == ".webm":
        return "comfy_webm"
    if suf == ".webp":
        return "comfy_webp"
    if suf == ".flac":
        return "comfy_flac"
    return "comfy_png"
