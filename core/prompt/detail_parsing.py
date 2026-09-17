"""Parsing helpers for file detail payload fields.

Resolves positive/negative prompts, resolution, model name and NovelAI V4
structured data from a raw file database row.
"""

import json
import re
from typing import Any

from core.prompt import parse_a1111_prompt, parse_novelai_v4_metadata

# Mirrors crates/meta-extract/src/lib.rs `is_nai_source`. Kept as a predicate
# rather than an inline tuple so the next source added does not have to be
# remembered in two places -- that is how the two sides drifted apart before.
#
# "novelai_v4" is the bare source for suffixes other than .png/.webp (e.g. a
# bridge save with image_format=jpg). "novelai_png"/"novelai_webp" are what the
# v3 extractor writes; they reach the same parser because NovelAI stores the
# generation parameters identically for v3. The remaining values are internal
# parser identifiers that only appear on rows polluted before E1.
_NAI_SOURCES = frozenset({
    "novelai_v4_png",
    "novelai_v4_webp",
    "novelai_v4",
    "novelai_png",
    "novelai_webp",
    "nai_webp",
    "nai_v4",
    "nai_v3",
})


def is_nai_source(meta_source: str | None) -> bool:
    """Return whether a DB source belongs to the NovelAI family."""
    return meta_source in _NAI_SOURCES

_COMFY_PARAM_LABELS = {
    "seed": "Seed",
    "steps": "Steps",
    "cfg": "CFG scale",
    "sampler_name": "Sampler",
    "scheduler": "Scheduler",
    "denoise": "Denoise",
    "guidance": "Guidance",
    "vae": "VAE",
    "clip_name1": "CLIP 1",
    "clip_name2": "CLIP 2",
    "ckpt_name": "Checkpoint",
    "diffusion_model": "Diffusion Model",
    "clip_type": "CLIP Type",
}


def _parse_comfy_parameters(raw_meta_json: str) -> tuple[dict[str, Any], str | None]:
    """Extract KSampler/loader params from a ComfyUI workflow JSON.

    Returns (parameters_dict, model_name_or_None). Keys are mapped to the
    same human-readable labels used by A1111 so the modal renderer
    displays them consistently.
    """
    try:
        obj = json.loads(raw_meta_json)
    except Exception:
        return {}, None

    from core.extract_core.comfyui_extract_helpers import extract_ksampler_params

    raw = extract_ksampler_params(obj)
    if not raw:
        return {}, None

    # Read 'model' without mutating the dict — extract_ksampler_params may
    # share/cache its return value; mutating it could affect other callers.
    model = raw.get("model")
    mapped: dict[str, Any] = {}
    for key, val in raw.items():
        if key == "model":
            continue
        label = _COMFY_PARAM_LABELS.get(key, key)
        mapped[label] = val
    return mapped, model


def resolve_detail_fields(file_row: dict[str, Any]) -> dict[str, Any]:
    """Parse a file DB row into structured detail fields."""
    resolution = None
    model = file_row["model_name"] or None
    raw_prompt = file_row["raw_prompt"] or ""
    raw_negative = file_row["raw_negative"] or ""
    raw_meta_json = file_row["raw_meta_json"]

    positive_only = raw_prompt
    parameters: dict[str, Any] = {}
    novelai_v4_data: dict[str, Any] | None = None

    if is_nai_source(file_row["meta_source"]) and raw_meta_json:
        nai_data = parse_novelai_v4_metadata(raw_meta_json)
        if nai_data:
            # Parameters and resolution are read for v3 too -- NovelAI writes
            # steps/sampler/seed/width/height regardless of the caption format.
            parameters = nai_data["parameters"]
            resolution = parameters.get("Size")
            # Everything below is v4-only: claiming a v4 model name or emitting a
            # v4 payload for a v3 image would be a lie.
            if nai_data.get("has_v4"):
                novelai_v4_data = nai_data
                if not model:
                    model = "NovelAI Diffusion V4.5"
                if not raw_negative:
                    raw_negative = _join_novelai_negative(novelai_v4_data)
    elif file_row["meta_source"] in ("comfy_png", "comfy_webp", "comfy_webm") and raw_meta_json:
        comfy_params, comfy_model = _parse_comfy_parameters(raw_meta_json)
        if comfy_params:
            parameters = comfy_params
        if not model and comfy_model:
            model = comfy_model
        # Derive resolution string from EmptyLatentImage width/height if available.
        if not resolution and "width" in parameters and "height" in parameters:
            import contextlib
            with contextlib.suppress(ValueError, TypeError):
                resolution = f"{int(parameters['width'])}x{int(parameters['height'])}"
    elif raw_prompt and ("Steps:" in raw_prompt or "Negative prompt:" in raw_prompt):
        parsed = parse_a1111_prompt(raw_prompt)
        positive_only = parsed["positive"]
        if not raw_negative and parsed["negative"]:
            raw_negative = parsed["negative"]
        parameters = parsed["parameters"]
        resolution = parameters.get("Size")
        if not model:
            model = parameters.get("Model")
    elif raw_prompt:
        size_match = re.search(r"Size:\s*(\d+x\d+)", raw_prompt)
        if size_match:
            resolution = size_match.group(1)
        model_match = re.search(r"Model:\s*([^,\n]+)", raw_prompt)
        if model_match:
            model = model_match.group(1).strip()

    return {
        "positive": positive_only,
        "negative": raw_negative,
        "resolution": resolution,
        "model": model,
        "parameters": parameters,
        "novelai_v4_data": novelai_v4_data,
    }


def build_novelai_payload(novelai_v4_data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Build a slim NovelAI V4 payload dict for API responses.

    The three-valued flags are emitted as explicit keys even when null -- a
    dropped key and an explicit null are different on the wire, and the Rust
    side emits the key either way.
    """
    if not novelai_v4_data:
        return None
    return {
        "base_caption": novelai_v4_data["base_caption"],
        "character_prompts": novelai_v4_data["character_prompts"],
        "negative_base": novelai_v4_data["negative_base"],
        "negative_characters": novelai_v4_data["negative_characters"],
        "vibe_transfer": novelai_v4_data["vibe_transfer"],
        "use_coords": novelai_v4_data.get("use_coords"),
        "negative_use_coords": novelai_v4_data.get("negative_use_coords"),
        "use_order": novelai_v4_data.get("use_order"),
    }


def _join_novelai_negative(novelai_v4_data: dict[str, Any]) -> str:
    """Join NovelAI V4 negative prompts into a single comma-separated string."""
    neg_parts: list[str] = []
    if novelai_v4_data.get("negative_base"):
        neg_parts.append(novelai_v4_data["negative_base"])
    for nc in novelai_v4_data.get("negative_characters", []):
        if nc.get("prompt"):
            neg_parts.append(nc["prompt"])
    return ", ".join(neg_parts)
