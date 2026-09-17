"""Stable Diffusion / ComfyUI metadata extraction helpers."""

import json
from typing import Any


def extract_sd(info: dict[str, Any]) -> tuple[str | None, str | None, str, str | None]:
    """Extract Stable Diffusion (A1111/Forge) metadata."""
    params_text = info.get("parameters", "")
    lines = params_text.split("\n")
    positive = None
    negative = None
    meta_dict: dict[str, str] = {}

    if lines:
        positive = lines[0].strip()

    for line in lines[1:]:
        if line.startswith("Negative prompt:"):
            negative = line.replace("Negative prompt:", "").strip()
        elif ":" in line:
            parts = line.split(",")
            for part in parts:
                if ":" in part:
                    key, value = part.split(":", 1)
                    meta_dict[key.strip()] = value.strip()

    fmt = "forge_sd" if "Forge" in params_text else "a1111_sd"
    return (positive, negative, fmt, json.dumps(meta_dict, ensure_ascii=False))


def extract_comfyui(info: dict[str, Any]) -> tuple[str | None, str | None, str, str | None]:
    """Extract ComfyUI metadata."""
    positive = None
    negative = None
    raw_meta: dict[str, Any] = {}

    if "prompt" in info:
        try:
            prompt_data = json.loads(info["prompt"]) if isinstance(info["prompt"], str) else info["prompt"]
            raw_meta["prompt"] = prompt_data

            if isinstance(prompt_data, dict):
                for node_data in prompt_data.values():
                    if isinstance(node_data, dict):
                        class_type = node_data.get("class_type", "")
                        inputs = node_data.get("inputs", {})

                        # Audio nodes (MMAudioSampler etc.) expose prompt /
                        # negative_prompt directly. Pick those up first since
                        # they are explicit; fall back to CLIPTextEncode-style
                        # 'text' inputs for image workflows.
                        explicit_pos = inputs.get("prompt") or inputs.get("positive_prompt")
                        explicit_neg = inputs.get("negative_prompt")
                        if isinstance(explicit_pos, str) and explicit_pos and not positive:
                            positive = explicit_pos
                        if isinstance(explicit_neg, str) and explicit_neg and not negative:
                            negative = explicit_neg

                        if "CLIPTextEncode" in class_type or "text" in class_type.lower():
                            text = inputs.get("text", "")
                            if isinstance(text, str) and text:
                                if not positive:
                                    positive = text
                                elif not negative:
                                    negative = text
        except (json.JSONDecodeError, TypeError):
            pass

    if "workflow" in info:
        try:
            workflow_data = json.loads(info["workflow"]) if isinstance(info["workflow"], str) else info["workflow"]
            raw_meta["workflow"] = workflow_data
        except (json.JSONDecodeError, TypeError):
            pass

    return (positive, negative, "comfyui_flux", json.dumps(raw_meta, ensure_ascii=False))
