"""NovelAI Image Generation API constants and request body builder."""

from __future__ import annotations

import random
from typing import Any

from .nai_uc_presets import (
    MODE_ANIME,
    expand_mode_prefix,
    expand_quality_tags,
    expand_uc_preset,
)

# -- Model constants ------------------------------------------------

MODELS: list[str] = [
    "nai-diffusion-5-full",
    "nai-diffusion-5-curated",
    "nai-diffusion-4-5-full",
    "nai-diffusion-4-5-curated",
    "nai-diffusion-4-full",
    "nai-diffusion-4-curated-preview",
]

MODEL_DISPLAY_NAMES: dict[str, str] = {
    "nai-diffusion-5-full": "NAI Diffusion 5 Full",
    "nai-diffusion-5-curated": "NAI Diffusion 5 Curated",
    "nai-diffusion-4-5-full": "NAI Diffusion 4.5 Full",
    "nai-diffusion-4-5-curated": "NAI Diffusion 4.5 Curated",
    "nai-diffusion-4-full": "NAI Diffusion 4 Full",
    "nai-diffusion-4-curated-preview": "NAI Diffusion 4 Curated",
}

# Variety+ (skip_cfg_above_sigma) uses a lower cutoff on the V4 base models.
# Anything newer (4.5, 5, ...) uses the higher one, so list the exceptions
# rather than pattern-matching the version out of the model id.
_V4_BASE_MODELS: frozenset[str] = frozenset({
    "nai-diffusion-4-full",
    "nai-diffusion-4-curated-preview",
})

SAMPLER_DISPLAY_NAMES: dict[str, str] = {
    "k_euler_ancestral": "Euler Ancestral",
    "k_euler": "Euler",
    "k_dpmpp_2m": "DPM++ 2M",
    "k_dpmpp_sde": "DPM++ SDE",
    "k_dpmpp_2s_ancestral": "DPM++ 2S Ancestral",
    "ddim": "DDIM",
}

NOISE_SCHEDULE_DISPLAY_NAMES: dict[str, str] = {
    "karras": "Karras",
    "exponential": "Exponential",
    "polyexponential": "Polyexponential",
    "native": "Native",
}

# -- Sampler constants ----------------------------------------------

SAMPLERS: list[str] = [
    "k_euler_ancestral",
    "k_euler",
    "k_dpmpp_2m",
    "k_dpmpp_sde",
    "k_dpmpp_2s_ancestral",
    "ddim",
]

# -- Noise schedule constants ---------------------------------------

NOISE_SCHEDULES: list[str] = [
    "karras",
    "exponential",
    "polyexponential",
    "native",
]

# -- Image format constants -----------------------------------------

IMAGE_FORMATS: list[str] = ["png", "webp", "jpg"]
DEFAULT_IMAGE_FORMAT = "png"

# -- Default parameter values ---------------------------------------

DEFAULT_STEPS = 28
DEFAULT_SCALE = 5.0
DEFAULT_CFG_RESCALE = 0.0
DEFAULT_WIDTH = 832
DEFAULT_HEIGHT = 1216
DEFAULT_SEED = -1
DEFAULT_N_SAMPLES = 1
# MODELS is ordered newest-first for the UI; the default is pinned so a
# newly added model never silently becomes the default.
DEFAULT_MODEL = "nai-diffusion-4-5-full"
DEFAULT_SAMPLER = SAMPLERS[0]
DEFAULT_NOISE_SCHEDULE = NOISE_SCHEDULES[0]


def _resolve_seed(seed: int) -> int:
    """Return a concrete seed (replace -1 with random)."""
    if seed < 0:
        return random.randint(0, 2**32 - 1)
    return seed


MAX_CHARACTERS = 6


def _build_char_captions(
    characters: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build positive and negative char_captions from a characters list.

    Returns ``(pos_captions, neg_captions)`` with matching length/indices.
    Characters whose positive prompt is empty are skipped.
    """
    if not characters:
        return [], []

    pos: list[dict[str, Any]] = []
    neg: list[dict[str, Any]] = []
    for entry in characters[:MAX_CHARACTERS]:
        char_prompt = (entry.get("prompt") or "").strip()
        if not char_prompt:
            continue
        char_neg = (entry.get("negative") or "").strip()
        center = entry.get("center") or {"x": 0.5, "y": 0.5}
        pos.append({"char_caption": char_prompt, "centers": [center]})
        neg.append({"char_caption": char_neg, "centers": [center]})
    return pos, neg


def build_request_body(
    prompt: str,
    negative_prompt: str,
    *,
    action: str = "generate",
    image: str | None = None,
    mask: str | None = None,
    strength: float = 0.7,
    noise: float = 0.0,
    characters: list[dict[str, Any]] | None = None,
    model: str = DEFAULT_MODEL,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    scale: float = DEFAULT_SCALE,
    sampler: str = DEFAULT_SAMPLER,
    steps: int = DEFAULT_STEPS,
    seed: int = DEFAULT_SEED,
    noise_schedule: str = DEFAULT_NOISE_SCHEDULE,
    cfg_rescale: float = DEFAULT_CFG_RESCALE,
    n_samples: int = DEFAULT_N_SAMPLES,
    reference_image_multiple: list[str] | None = None,
    reference_information_extracted_multiple: list[float] | None = None,
    reference_strength_multiple: list[float] | None = None,
    use_type_multiple: list[str] | None = None,
    quality_toggle: bool = True,
    mode: str = MODE_ANIME,
    uc_preset: int = 0,
    dynamic_thresholding: bool = False,
    uncond_scale: float = 1.0,
    variety_boost: bool = False,
    image_format: str = DEFAULT_IMAGE_FORMAT,
) -> dict[str, Any]:
    """Build a NAI V4 image generation request body.

    Returns a dict suitable for POST to ``/ai/generate-image``.
    The format follows NovelAI V4 API spec with ``v4_prompt`` /
    ``v4_negative_prompt`` structure.
    """
    resolved_seed = _resolve_seed(seed)
    # NovelAI expands the UC preset and quality tags client side — prepending
    # the preset to the undesired content and appending the tags to the prompt.
    # Sending only the integer/boolean applies neither, so do it here, where
    # every caller (UI, MCP, LAN peer) passes through.
    negative_prompt, uc_preset = expand_uc_preset(
        model, uc_preset, negative_prompt
    )
    # NovelAI's Furry mode is just the `fur dataset` tag at the very start of
    # the base prompt, and the quality tags go at the very end.
    prompt = expand_mode_prefix(mode, prompt)
    prompt, quality_toggle = expand_quality_tags(model, quality_toggle, prompt)
    pos_chars, neg_chars = _build_char_captions(characters)
    use_coords = any(
        c.get("center") for c in (characters or [])
    )

    v4_prompt = {
        "caption": {
            "base_caption": prompt,
            "char_captions": pos_chars,
        },
        "use_coords": use_coords,
        "use_order": True,
    }

    v4_negative = {
        "caption": {
            "base_caption": negative_prompt,
            "char_captions": neg_chars,
        },
        "use_coords": use_coords,
        "use_order": True,
    }

    parameters: dict[str, Any] = {
        "width": width,
        "height": height,
        "scale": scale,
        "sampler": sampler,
        "steps": steps,
        "seed": resolved_seed,
        "n_samples": n_samples,
        "noise_schedule": noise_schedule,
        "cfg_rescale": cfg_rescale,
        "sm": False,
        "sm_dyn": False,
        "skip_cfg_above_sigma": None,
        "dynamic_thresholding": dynamic_thresholding,
        "controlnet_strength": 1.0,
        "legacy": False,
        "add_original_image": True,
        "uncond_scale": uncond_scale,
        "qualityToggle": quality_toggle,
        "ucPreset": uc_preset,
        "negative_prompt": negative_prompt,
        "params_version": 3,
        "v4_prompt": v4_prompt,
        "v4_negative_prompt": v4_negative,
        "use_coords": use_coords,
        "image_format": image_format if image_format in IMAGE_FORMATS else DEFAULT_IMAGE_FORMAT,
    }

    # Variety Boost → skip_cfg_above_sigma auto-calculation
    if variety_boost:
        parameters["skip_cfg_above_sigma"] = (
            19 if model in _V4_BASE_MODELS else 58
        )

    # Vibe Transfer / Precise Reference (V4 parallel-array schema).
    # All reference images — single Vibe Transfer entry plus up to four
    # Precise Reference entries — flow through this one path. NAI V4
    # rejects the V3 single-key form (``reference_image`` etc.) with a
    # bare 500 Internal Server Error, so we never emit it.
    if reference_image_multiple:
        parameters["reference_image_multiple"] = list(
            reference_image_multiple)
        n = len(reference_image_multiple)
        info_list = (reference_information_extracted_multiple
                     or [1.0] * n)
        strength_list = reference_strength_multiple or [0.6] * n
        parameters["reference_information_extracted_multiple"] = [
            float(x) for x in info_list[:n]
        ]
        parameters["reference_strength_multiple"] = [
            float(x) for x in strength_list[:n]
        ]
        if use_type_multiple:
            parameters["use_type_multiple"] = [
                str(t) for t in use_type_multiple[:n]
            ]

    # Inpainting parameters (takes priority over img2img)
    if action == "inpaint" and image and mask:
        parameters["image"] = image
        parameters["mask"] = mask
        parameters["strength"] = strength
        parameters["noise"] = noise
        parameters["extra_noise_seed"] = resolved_seed
    # img2img parameters
    elif action == "img2img" and image:
        parameters["image"] = image
        parameters["strength"] = strength
        parameters["noise"] = noise
        parameters["extra_noise_seed"] = resolved_seed

    return {
        "input": prompt,
        "model": model,
        "action": action if action in ("generate", "img2img", "inpaint") else "generate",
        "parameters": parameters,
    }
