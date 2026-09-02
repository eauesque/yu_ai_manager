"""builtin-comfyui package marker and shared constants."""

# Known meta_source values produced by infer_comfy_meta_source()
COMFY_META_SOURCES: frozenset[str] = frozenset({
    "comfy_png",
    "comfy_webp",
    "comfy_webm",
    "comfy_flac",
})
