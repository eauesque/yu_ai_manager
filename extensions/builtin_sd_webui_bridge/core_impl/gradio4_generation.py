"""Generation and response helpers for the Forge Gradio 4 client."""

from __future__ import annotations

import logging
from typing import Any

from core.bridge_core import BridgeHTTPError

from .gradio4_io import fetch_file_as_b64, parse_seed, read_file_as_b64, set_arg

logger = logging.getLogger(__name__)


def build_txt2img_args(defaults: list, label_map: dict[str, int], prompt: str, negative_prompt: str, steps: int, sampler_name: str, cfg_scale: float, width: int, height: int, seed: int, extra: dict[str, Any] | None = None) -> list:
    args = list(defaults or [])
    set_arg(args, label_map, "Prompt", prompt)
    set_arg(args, label_map, "Negative prompt", negative_prompt)
    set_arg(args, label_map, "Sampling steps", steps)
    set_arg(args, label_map, "Sampling method", sampler_name)
    set_arg(args, label_map, "CFG Scale", cfg_scale)
    set_arg(args, label_map, "Width", width)
    set_arg(args, label_map, "Height", height)
    set_arg(args, label_map, "Seed", seed)
    extra = extra or {}
    if extra.get("enable_hr"):
        set_arg(args, label_map, "Hires. fix", True)
        set_arg(args, label_map, "Denoising strength", float(extra.get("denoising_strength", 0.7)))
        set_arg(args, label_map, "Upscale by", float(extra.get("hr_scale", 2.0)))
        set_arg(args, label_map, "Upscaler", str(extra.get("hr_upscaler", "Latent")))
        set_arg(args, label_map, "Hires steps", int(extra.get("hr_second_pass_steps", 0)))
    return args


def build_img2img_args(config: dict, prompt: str, negative_prompt: str, steps: int, sampler_name: str, cfg_scale: float, width: int, height: int, seed: int, denoising_strength: float) -> list:
    deps = config.get("dependencies", [])
    components = {c["id"]: c for c in config.get("components", []) if "id" in c}
    img2img_dep = next((dep for dep in deps if dep.get("api_name") == "img2img"), None)
    if img2img_dep is None:
        raise BridgeHTTPError(501, "img2img not available")

    args = []
    label_map: dict[str, int] = {}
    for idx, comp_id in enumerate(img2img_dep.get("inputs", [])):
        props = components.get(comp_id, {}).get("props", {})
        args.append(props.get("value"))
        label = props.get("label", "")
        if label:
            label_map[label] = idx

    set_arg(args, label_map, "Prompt", prompt)
    set_arg(args, label_map, "Negative prompt", negative_prompt)
    set_arg(args, label_map, "Sampling steps", steps)
    set_arg(args, label_map, "Sampling method", sampler_name)
    set_arg(args, label_map, "CFG Scale", cfg_scale)
    set_arg(args, label_map, "Width", width)
    set_arg(args, label_map, "Height", height)
    set_arg(args, label_map, "Seed", seed)
    set_arg(args, label_map, "Denoising strength", denoising_strength)
    return args


def normalize_response(api_url: str, result_data: Any, prompt: str, negative: str, seed: int) -> dict[str, Any]:
    """Convert Gradio SSE result to sdapi-compatible format."""
    if not isinstance(result_data, list) or not result_data:
        return {"images": [], "parameters": {"seed": seed}}

    gallery = result_data[0] if result_data else []
    images_b64: list[str] = []
    if isinstance(gallery, list):
        for item in gallery:
            b64 = extract_image_b64(api_url, item)
            if b64:
                images_b64.append(b64)

    used_seed = parse_seed(result_data[1] if len(result_data) > 1 else "", seed)
    return {
        "images": images_b64,
        "parameters": {"prompt": prompt, "negative_prompt": negative, "seed": used_seed},
    }


def extract_image_b64(api_url: str, item: Any) -> str | None:
    if isinstance(item, str):
        return item.split(",", 1)[-1] if item.startswith("data:image") else item
    if not isinstance(item, dict):
        return None

    image_info = item.get("image", item)
    if isinstance(image_info, dict):
        path = image_info.get("path", "")
        if path:
            b64 = read_file_as_b64(path)
            if b64:
                return b64
        url = image_info.get("url", "")
        if url:
            return fetch_file_as_b64(api_url, url)
    return None
