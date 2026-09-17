"""Extract Simple mode parameters from a ComfyUI API-format workflow.

Walks the workflow JSON to find known node types and extracts parameters
that can be mapped to the Simple mode UI fields.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def extract_simple_params(workflow: dict) -> dict[str, Any]:
    """Extract Simple mode parameters from a ComfyUI API-format workflow.

    Parameters
    ----------
    workflow:
        ComfyUI API format: ``{node_id: {"class_type": ..., "inputs": ...}}``.

    Returns
    -------
    dict
        Extracted parameters. Keys correspond to Simple mode field names.
        Only present if found in the workflow.
    """
    if not workflow:
        return {}

    params: dict[str, Any] = {}
    nodes_by_type = _index_by_type(workflow)

    # -- Model source --
    _extract_model_source(nodes_by_type, params)

    # -- KSampler params --
    ksampler = _find_first(nodes_by_type, "KSampler", "KSamplerAdvanced")
    if ksampler:
        inp = ksampler.get("inputs", {})
        for key in ("seed", "steps", "cfg", "sampler_name", "scheduler"):
            if key in inp:
                params[key] = inp[key]

        # Prompt extraction via KSampler backtracking
        _extract_prompts_via_ksampler(workflow, ksampler, params)
    else:
        # Fallback: _meta.title
        _extract_prompts_via_title(nodes_by_type, params)

    # -- EmptyLatentImage (width/height) --
    latent = _find_first(nodes_by_type, "EmptyLatentImage")
    if latent:
        inp = latent.get("inputs", {})
        if "width" in inp:
            params["width"] = inp["width"]
        if "height" in inp:
            params["height"] = inp["height"]

    return params


def _set_str(params: dict, key: str, value: Any) -> None:
    """Set params[key] only if value is a non-empty string (not a node reference)."""
    if isinstance(value, str) and value:
        params[key] = value


def _index_by_type(workflow: dict) -> dict[str, list]:
    """Group nodes by class_type."""
    by_type: dict[str, list] = {}
    for _node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type", "")
        by_type.setdefault(ct, []).append(node)
    return by_type


def _find_first(by_type: dict, *type_names: str) -> dict | None:
    """Return first node matching any of the given type names."""
    for name in type_names:
        nodes = by_type.get(name, [])
        if nodes:
            return nodes[0]
    return None


def _extract_model_source(
    by_type: dict[str, list], params: dict[str, Any],
) -> None:
    """Extract checkpoint or separate-load model info."""
    unet = _find_first(by_type, "UNETLoader")
    if unet:
        _set_str(params, "diffusion_model", unet["inputs"].get("unet_name"))
        _set_str(params, "weight_dtype", unet["inputs"].get("weight_dtype"))

    dual = _find_first(by_type, "DualCLIPLoader")
    if dual:
        inp = dual["inputs"]
        _set_str(params, "text_encoder_1", inp.get("clip_name1"))
        _set_str(params, "text_encoder_2", inp.get("clip_name2"))
        _set_str(params, "clip_type", inp.get("type"))
    else:
        clip = _find_first(by_type, "CLIPLoader")
        if clip:
            _set_str(params, "text_encoder_1", clip["inputs"].get("clip_name"))
            _set_str(params, "clip_type", clip["inputs"].get("type"))

    ckpt = _find_first(by_type, "CheckpointLoaderSimple")
    if ckpt and not unet:
        _set_str(params, "ckpt_name", ckpt["inputs"].get("ckpt_name"))

    vae = _find_first(by_type, "VAELoader")
    if vae:
        # vae_name can be a node reference (list) when VAE is wired dynamically.
        # Only accept literal string values.
        _set_str(params, "vae_name", vae["inputs"].get("vae_name"))


def _extract_prompts_via_ksampler(
    workflow: dict, ksampler: dict, params: dict[str, Any],
) -> None:
    """Trace KSampler's positive/negative inputs to find CLIPTextEncode."""
    inp = ksampler.get("inputs", {})

    pos_ref = inp.get("positive")
    neg_ref = inp.get("negative")

    if isinstance(pos_ref, list) and len(pos_ref) >= 2:
        text = _trace_to_clip_text(workflow, str(pos_ref[0]), pos_ref[1])
        if text is not None:
            params["prompt"] = text

    if isinstance(neg_ref, list) and len(neg_ref) >= 2:
        text = _trace_to_clip_text(workflow, str(neg_ref[0]), neg_ref[1])
        if text is not None:
            params["negative_prompt"] = text


def _trace_to_clip_text(
    workflow: dict, node_id: str, output_slot: int = 0,
    depth: int = 0,
) -> str | None:
    """Recursively trace a node reference to find CLIPTextEncode text.

    Handles indirect links through ControlNetApplyAdvanced etc.
    Uses output_slot to pick the correct input when a node has
    multiple outputs (e.g. ControlNetApplyAdvanced: 0=positive, 1=negative).
    """
    if depth > 10:
        return None

    node = workflow.get(node_id)
    if not isinstance(node, dict):
        return None

    if node.get("class_type") == "CLIPTextEncode":
        return node.get("inputs", {}).get("text")

    # Map output slot to the matching input key for passthrough nodes
    inp = node.get("inputs", {})
    slot_keys = ("positive", "negative")
    tried_refs: set[tuple[str, int]] = set()

    if output_slot < len(slot_keys):
        key = slot_keys[output_slot]
        ref = inp.get(key)
        if isinstance(ref, list) and len(ref) >= 2:
            ref_key = (str(ref[0]), int(ref[1]))
            tried_refs.add(ref_key)
            result = _trace_to_clip_text(
                workflow, ref_key[0], ref_key[1], depth + 1)
            if result is not None:
                return result

    # Fallback: try remaining positive/negative inputs not already visited.
    for key in slot_keys:
        ref = inp.get(key)
        if isinstance(ref, list) and len(ref) >= 2:
            ref_key = (str(ref[0]), int(ref[1]))
            if ref_key in tried_refs:
                continue
            tried_refs.add(ref_key)
            result = _trace_to_clip_text(
                workflow, ref_key[0], ref_key[1], depth + 1)
            if result is not None:
                return result

    return None


def _extract_prompts_via_title(
    by_type: dict[str, list], params: dict[str, Any],
) -> None:
    """Fallback: use _meta.title to identify positive/negative."""
    clip_nodes = by_type.get("CLIPTextEncode", [])

    for node in clip_nodes:
        title = (node.get("_meta", {}).get("title", "") or "").lower()
        text = node.get("inputs", {}).get("text", "")
        if "positive" in title and "prompt" not in params:
            params["prompt"] = text
        elif "negative" in title and "negative_prompt" not in params:
            params["negative_prompt"] = text

    # Last resort: first = positive, second = negative
    if "prompt" not in params and len(clip_nodes) >= 1:
        params["prompt"] = clip_nodes[0].get("inputs", {}).get("text", "")
    if "negative_prompt" not in params and len(clip_nodes) >= 2:
        params["negative_prompt"] = clip_nodes[1].get("inputs", {}).get(
            "text", "")
