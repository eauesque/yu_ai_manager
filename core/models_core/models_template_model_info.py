"""Model-name/hash extraction helpers for templates."""

import json
import logging
import re

logger = logging.getLogger(__name__)

_RE_A1111_MODEL = re.compile(r",\s*Model:\s*([^,\n]+)")
_RE_A1111_HASH = re.compile(r",\s*Model hash:\s*([^,\n]+)")
_RE_NAI_SOURCE = re.compile(r"^(.+?)\s+([A-Fa-f0-9]{6,})$")


def extract_model_from_prompt(raw_prompt: str | None) -> tuple[str | None, str | None]:
    """Extract Model name/hash from A1111 Parameters text (last line of raw_prompt)."""
    if not raw_prompt or "Steps:" not in raw_prompt:
        return (None, None)
    # Only search in the Parameters section (after last "Steps:")
    steps_idx = raw_prompt.rfind("Steps:")
    params_section = raw_prompt[steps_idx:]
    m = _RE_A1111_MODEL.search(params_section)
    if not m:
        return (None, None)
    model_name = m.group(1).strip()
    model_hash = None
    h = _RE_A1111_HASH.search(params_section)
    if h:
        model_hash = h.group(1).strip()
    return (model_name or None, model_hash or None)


def extract_model_info(raw_meta_json: str | None, fmt: str) -> tuple[str | None, str | None]:
    if not raw_meta_json:
        return (None, None)

    try:
        meta = json.loads(raw_meta_json)
        if fmt == "nai" or "model" in meta:
            return (meta.get("model"), None)
        # NAI v4: Source = "NovelAI Diffusion V4.5 4BDE2A90"
        if "Source" in meta and isinstance(meta.get("Software"), str) and "NovelAI" in meta["Software"]:
            source = meta["Source"].strip()
            if source:
                m = _RE_NAI_SOURCE.search(source)
                if m:
                    return (m.group(1).strip(), m.group(2).strip())
                return (source, None)
        if "Model" in meta:
            return (meta.get("Model"), meta.get("Model hash"))
        if fmt == "tensor_art" or "baseModel" in meta:
            bm = meta.get("baseModel", {})
            if isinstance(bm, dict):
                model_file = bm.get("modelFileName", "")
                base_model = bm.get("baseModel", "")
                label = bm.get("label", "")
                model_hash = bm.get("hash", "") or bm.get("modelId", "")
                name = model_file or base_model or (label if label != "Base" else "")
                if name:
                    return (name, model_hash or None)
            # tensor_art fallback: try modelName at top level
            if fmt == "tensor_art":
                for key in ("modelName", "model_name", "model"):
                    v = meta.get(key)
                    if isinstance(v, str) and v:
                        return (v, None)

        model_name = extract_comfyui_model(meta)
        if model_name:
            return (model_name, None)
    except (json.JSONDecodeError, TypeError) as e:
        logger.debug(f"Error parsing metadata for model extraction: {e}")
    return (None, None)


def extract_comfyui_model(meta: dict) -> str | None:
    _MODEL_EXTS = (".safetensors", ".ckpt", ".pt", ".pth", ".bin")

    def _strip_ext(s: str) -> str:
        for ext in _MODEL_EXTS:
            if s.endswith(ext):
                s = s[: -len(ext)]
                break
        # Strip leading path components (e.g. "models/checkpoints/foo" → "foo")
        return s.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]

    # Top-level shortcut keys
    for key in ("checkpoint", "ckpt_name"):
        v = meta.get(key)
        if isinstance(v, str) and v:
            return _strip_ext(v)

    # ComfyUI prompt graph — node-based extraction
    if "prompt" in meta:
        prompt_data = meta.get("prompt", {})
        if isinstance(prompt_data, dict):
            # Priority 1: CheckpointLoader variants
            _LOADER_KEYS = ("ckpt_name", "checkpoint", "unet_name")
            for node_data in prompt_data.values():
                if not isinstance(node_data, dict):
                    continue
                class_type = node_data.get("class_type", "")
                inputs = node_data.get("inputs", {})
                if not isinstance(inputs, dict):
                    continue
                if "CheckpointLoader" in class_type or "UNETLoader" in class_type or "Loader" in class_type:
                    for key in _LOADER_KEYS:
                        ckpt = inputs.get(key)
                        if isinstance(ckpt, str) and ckpt:
                            return _strip_ext(ckpt)
            # Priority 2: Any node with model file inputs
            for node_data in prompt_data.values():
                if not isinstance(node_data, dict):
                    continue
                inputs = node_data.get("inputs", {})
                if not isinstance(inputs, dict):
                    continue
                for key in ("model", "model_name"):
                    val = inputs.get(key)
                    if isinstance(val, str) and val.endswith(_MODEL_EXTS):
                        return _strip_ext(val)

    if "workflow" in meta:
        wf = meta.get("workflow", {})
        if isinstance(wf, dict) and "model" in wf:
            val = wf.get("model")
            if isinstance(val, str):
                return _strip_ext(val)
    return None
