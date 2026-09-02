"""Discovery API routes for ComfyUI Bridge.

Exposes LoRA, Embedding, and Custom Node lists from the
connected ComfyUI instance.
"""

from __future__ import annotations

import asyncio
import logging

from core.extensions_core.extensions_admin import get_extension_config_value
from quart import Blueprint, request

from core.infra_core.api_errors import api_error, api_success

from .comfyui_checkpoint_inspect import auto_detect_models_root, inspect_checkpoint
from .comfyui_client import ComfyUIClient

_EXT_NAME = "builtin-comfyui-bridge"

logger = logging.getLogger(__name__)


# Discovery endpoints invoke synchronous urllib-backed HTTP calls against the
# upstream ComfyUI server. Some of these (e.g. /object_info/LoraLoader,
# /object_info root) are heavy on the first call because ComfyUI lazily
# enumerates the model directories. Running them directly inside an async
# handler blocks the entire event loop, so every other request — including the
# next discovery tab the user clicks — gets stuck behind it. Offloading to a
# thread keeps the server responsive while the upstream scan finishes.
async def _run_sync(fn, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)


def register_comfyui_discovery_routes(
    bp: Blueprint,
    make_client,
) -> None:
    """Register discovery endpoints on the given blueprint.

    Parameters
    ----------
    bp:
        The ComfyUI Bridge Blueprint.
    make_client:
        Callable that returns a configured :class:`ComfyUIClient`.
    """

    @bp.route("/api/loras")
    async def api_loras():
        q = (request.args.get("q") or "").strip().lower()
        client: ComfyUIClient = await _run_sync(make_client)
        loras = await _run_sync(client.list_loras)
        if q:
            loras = [n for n in loras if q in n.lower()]
        return api_success({"loras": loras})

    @bp.route("/api/embeddings")
    async def api_embeddings():
        q = (request.args.get("q") or "").strip().lower()
        client: ComfyUIClient = await _run_sync(make_client)
        embeddings = await _run_sync(client.list_embeddings)
        if q:
            embeddings = [n for n in embeddings if q in n.lower()]
        return api_success({"embeddings": embeddings})

    @bp.route("/api/custom-nodes")
    async def api_custom_nodes():
        q = (request.args.get("q") or "").strip().lower()
        client: ComfyUIClient = await _run_sync(make_client)
        nodes = await _run_sync(client.list_custom_nodes)
        if q:
            nodes = [n for n in nodes if q in n.get("name", "").lower() or q in n.get("category", "").lower()]
        return api_success({"nodes": nodes})

    @bp.route("/api/diffusion-models")
    async def api_diffusion_models():
        q = (request.args.get("q") or "").strip().lower()
        client: ComfyUIClient = await _run_sync(make_client)
        models = await _run_sync(client.list_diffusion_models)
        if q:
            models = [n for n in models if q in n.lower()]
        return api_success({"models": models})

    @bp.route("/api/text-encoders")
    async def api_text_encoders():
        q = (request.args.get("q") or "").strip().lower()
        client: ComfyUIClient = await _run_sync(make_client)
        encoders = await _run_sync(client.list_text_encoders)
        if q:
            encoders = [n for n in encoders if q in n.lower()]
        return api_success({"encoders": encoders})

    @bp.route("/api/clip-types")
    async def api_clip_types():
        client: ComfyUIClient = await _run_sync(make_client)
        types = await _run_sync(client.list_clip_types)
        return api_success({"clip_types": types})

    @bp.route("/api/weight-dtypes")
    async def api_weight_dtypes():
        client: ComfyUIClient = await _run_sync(make_client)
        dtypes = await _run_sync(client.list_weight_dtypes)
        return api_success({"weight_dtypes": dtypes})

    @bp.route("/api/controlnets")
    async def api_controlnets():
        q = (request.args.get("q") or "").strip().lower()
        client: ComfyUIClient = await _run_sync(make_client)
        models = await _run_sync(client.list_controlnets)
        if q:
            models = [n for n in models if q in n.lower()]
        return api_success({"models": models})

    @bp.route("/api/upscale-models")
    async def api_upscale_models():
        q = (request.args.get("q") or "").strip().lower()
        client: ComfyUIClient = await _run_sync(make_client)
        models = await _run_sync(client.list_upscale_models)
        if q:
            models = [n for n in models if q in n.lower()]
        return api_success({"models": models})

    @bp.route("/api/discovery/models")
    async def api_discovery_models():
        """Generic model discovery endpoint — returns models for any loader type."""
        model_type = (request.args.get("type") or "").strip()
        q = (request.args.get("q") or "").strip().lower()
        if not model_type:
            return api_error("type parameter is required", 400)

        _LOADER_MAP = {
            "diffusion_models": ("UNETLoader", "unet_name"),
            "text_encoders": ("CLIPLoader", "clip_name"),
            "controlnet": ("ControlNetLoader", "control_net_name"),
            "upscale_models": ("UpscaleModelLoader", "model_name"),
            "loras": ("LoraLoader", "lora_name"),
            "vae": ("VAELoader", "vae_name"),
            "checkpoints": ("CheckpointLoaderSimple", "ckpt_name"),
            "clip": ("CLIPLoader", "clip_name"),
            "clip_vision": ("CLIPVisionLoader", "clip_name"),
            "hypernetworks": ("HypernetworkLoader", "hypernetwork_name"),
            "style_models": ("StyleModelLoader", "style_model_name"),
            "unet": ("UNETLoader", "unet_name"),
            "gligen": ("GLIGENLoader", "gligen_name"),
        }

        client: ComfyUIClient = await _run_sync(make_client)
        mapping = _LOADER_MAP.get(model_type)
        if mapping:
            models = await _run_sync(client.list_models_by_loader, mapping[0], mapping[1])
        else:
            models = []

        if q:
            models = [n for n in models if q in n.lower()]
        return api_success({"models": models, "type": model_type})

    @bp.route("/api/checkpoint-info")
    async def api_checkpoint_info():
        """Inspect a checkpoint's safetensors header to identify model family.

        Falls back to ``source: "unavailable"`` when the file cannot be
        accessed locally (remote ComfyUI, or models_root not configured).
        The frontend should then degrade to filename-based detection and
        warn the user that the family guess is not verified.
        """
        name = (request.args.get("name") or "").strip()
        if not name:
            return api_error("name parameter is required", 400)

        models_root = get_extension_config_value(_EXT_NAME, "models_root", "")
        if not models_root:
            api_url = get_extension_config_value(
                _EXT_NAME, "api_url", "http://127.0.0.1:8188"
            )
            models_root = auto_detect_models_root(api_url)

        info = await _run_sync(inspect_checkpoint, name, models_root)
        return api_success(info)
