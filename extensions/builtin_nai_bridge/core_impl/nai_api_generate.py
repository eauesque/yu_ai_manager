"""NAI Bridge generate endpoint and parameter helpers."""

from __future__ import annotations

import base64
import contextlib
import logging
import time
from typing import Any

from core.extensions_core.extensions_admin import get_extension_config_value

from core.bridge_core.bridge_import import (
    import_saved_files_async,
    import_saved_files_sync,
)
from core.bridge_core.prompt_expand import expand_text, maybe_expand_prompt
from core.event_bus import emit
from core.event_bus.event_types import GEN_COMPLETE, GEN_ERROR, GEN_SUBMIT
from core.infra_core.api_errors import api_error, api_success
from core.infra_core.blocking_tasks import run_blocking_sync, run_long_blocking_sync

from .nai_client import NAIClient
from .nai_cost import is_opus_free_generation
from .nai_params import MODELS
from .nai_save import save_images
from .nai_uc_presets import GEN_V5, MODE_ANIME, MODE_PREFIXES, model_generation

logger = logging.getLogger(__name__)

_EXT_NAME = "builtin-nai-bridge"
_BRIDGE_TAG = "nai-api"


def _copy_param(src: dict, dst: dict, key: str, typ: type) -> None:
    """Copy a parameter from src to dst, casting to typ if present."""
    if key in src and src[key] is not None:
        with contextlib.suppress(ValueError, TypeError):
            dst[key] = typ(src[key])


def _snap64(val: int | float) -> int:
    """Round a pixel dimension to the nearest multiple of 64.

    Stable Diffusion derived models (NAI included) downscale by 8 in the VAE
    and again inside the UNet, so the API rejects dimensions that are not a
    multiple of 64. Snap here rather than at the call sites so custom sizes
    typed into the bridge UI are corrected on every path.
    """
    return max(64, (int(val) + 32) // 64 * 64)


def _build_generate_params(data: dict, params: dict[str, Any]) -> None:
    """Copy and validate standard generation parameters from request data.

    Server-side clamping is applied to Anlas-consuming fields (steps,
    n_samples, width, height) so a crafted request cannot trigger runaway
    credit consumption.  Other fields are type-cast only.
    """
    # model: validate against known allowlist; fall back to first model if invalid.
    raw_model = data.get("model")
    if raw_model is not None:
        model_str = str(raw_model)
        params["model"] = model_str if model_str in MODELS else MODELS[0]

    _copy_param(data, params, "sampler", str)
    _copy_param(data, params, "noise_schedule", str)
    # Dataset mode (Anime / Furry). Validate against the known set: an unknown
    # value must not reach the prompt as a stray tag.
    raw_mode = data.get("mode")
    if raw_mode is not None:
        params["mode"] = (
            str(raw_mode) if str(raw_mode) in MODE_PREFIXES else MODE_ANIME
        )

    # Numeric fields with safety clamps.
    def _clamp(val: Any, default: int | float, lo: int | float, hi: int | float,
               typ: type) -> int | float:
        try:
            return max(lo, min(typ(val), hi))  # type: ignore[arg-type]
        except (ValueError, TypeError):
            return default

    if "steps" in data:
        params["steps"] = _clamp(data["steps"], 28, 1, 50, int)
    if "scale" in data:
        params["scale"] = _clamp(data["scale"], 7.0, 0.0, 10.0, float)
    if "cfg_rescale" in data:
        params["cfg_rescale"] = _clamp(data["cfg_rescale"], 0.0, 0.0, 1.0, float)
    if "width" in data:
        params["width"] = _snap64(_clamp(data["width"], 832, 64, 2048, int))
    if "height" in data:
        params["height"] = _snap64(_clamp(data["height"], 1216, 64, 2048, int))
    if "seed" in data:
        # -1 is the "random seed" sentinel the UI sends when the seed box is
        # empty; build_request_body resolves it. Clamping the low bound to 0
        # turned every random request into the fixed seed 0.
        params["seed"] = _clamp(data["seed"], -1, -1, 2**32 - 1, int)
    # n_samples: cap to 1 per call (client JS loops); server-side guard prevents
    # a single crafted request from consuming many Anlas at once.
    if "n_samples" in data:
        params["n_samples"] = _clamp(data["n_samples"], 1, 1, 1, int)

    _copy_param(data, params, "quality_toggle", bool)
    _copy_param(data, params, "uc_preset", int)
    _copy_param(data, params, "dynamic_thresholding", bool)
    _copy_param(data, params, "uncond_scale", float)
    _copy_param(data, params, "variety_boost", bool)
    _copy_param(data, params, "image_format", str)


def _build_img2img_params(data: dict, params: dict[str, Any]) -> None:
    """Extract img2img / inpaint parameters."""
    i2i_image = data.get("image")
    i2i_mask = data.get("mask")
    if i2i_image and isinstance(i2i_image, str):
        if i2i_mask and isinstance(i2i_mask, str):
            params["action"] = "inpaint"
            params["mask"] = i2i_mask
        else:
            params["action"] = "img2img"
        params["image"] = i2i_image
        _copy_param(data, params, "strength", float)
        _copy_param(data, params, "noise", float)


def _build_reference_params(data: dict, params: dict[str, Any]) -> None:
    """Extract vibe transfer and precise reference parameters.

    NAI V4 / V4.5 expects three parallel arrays under ``parameters``:
    ``reference_image_multiple`` (base64 strings), and
    ``reference_information_extracted_multiple`` /
    ``reference_strength_multiple`` (floats). The V3 single-key form
    (``reference_image`` etc.) causes a 500 on V4 models, so we always
    emit the V4 parallel-array form here.
    """
    images: list[str] = []
    infos: list[float] = []
    strengths: list[float] = []
    types: list[str] = []

    # Vibe Transfer (single image w/ explicit strength + info)
    ref_image = data.get("reference_image")
    if ref_image and isinstance(ref_image, str):
        images.append(ref_image)
        try:
            infos.append(float(data.get(
                "reference_information_extracted", 1.0)))
        except (ValueError, TypeError):
            infos.append(1.0)
        try:
            strengths.append(float(data.get("reference_strength", 0.6)))
        except (ValueError, TypeError):
            strengths.append(0.6)
        types.append("character_and_style")  # Vibe Transfer has no type selector

    # Precise Reference (multiple images; fidelity locked at encode-vibe time)
    raw_refs = data.get("reference_image_multiple")
    if isinstance(raw_refs, list):
        for ref in raw_refs[:4]:
            if not (isinstance(ref, dict) and ref.get("image")):
                continue
            images.append(ref["image"])
            try:
                infos.append(float(ref.get("information_extracted", 1.0)))
            except (ValueError, TypeError):
                infos.append(1.0)
            try:
                strengths.append(float(ref.get("strength", 1.0)))
            except (ValueError, TypeError):
                strengths.append(1.0)
            ref_type = str(ref.get("type") or "character_and_style")
            if ref_type not in ("character_and_style", "character", "style"):
                ref_type = "character_and_style"
            types.append(ref_type)

    if images:
        # Raw base64 images are stashed here; NAIClient.generate()
        # routes each through /ai/encode-vibe before submitting the
        # generation request (V4 vibe transfer mandates pre-encoded
        # vibe bundles in this field).
        params["reference_image_multiple"] = images
        params["reference_information_extracted_multiple"] = infos
        params["reference_strength_multiple"] = strengths
        params["use_type_multiple"] = types


def _build_character_params(
    data: dict, params: dict[str, Any],
    _seed: int, extra_wc: dict | None,
) -> None:
    """Extract character prompt parameters with wildcard expansion."""
    raw_characters = data.get("characters")
    if not isinstance(raw_characters, list):
        return
    characters = []
    for entry in raw_characters:
        if not isinstance(entry, dict):
            continue
        cp = (entry.get("prompt") or "").strip()
        if not cp:
            continue
        characters.append({
            "prompt": cp,
            "negative": (entry.get("negative") or "").strip(),
            "center": entry.get("center") or {"x": 0.5, "y": 0.5},
        })
    if characters:
        _wc_seed = _seed if _seed not in (-1, None) else None
        for char in characters:
            if char.get("prompt"):
                char["prompt"] = expand_text(
                    char["prompt"], seed=_wc_seed,
                    extra_wildcards=extra_wc)
        params["characters"] = characters


def _convert_images_if_needed(raw_images: list[bytes], image_format: str) -> list[bytes]:
    """Convert generated images to the requested format when required."""
    if image_format != "jpg" or not raw_images:
        return raw_images
    from core.bridge_core.bridge_save import _convert_image
    return [_convert_image(img, "jpg") for img in raw_images]


async def handle_generate(data: dict, get_token_fn) -> tuple:
    """Handle the /api/generate endpoint logic.

    Sweep contract: when the request includes ``sweep_meta``, save indexing
    blocks until completion and the response includes
    ``saved_items: [{path, file_id}, ...]``. Without ``sweep_meta``, indexing
    is fire-and-forget so non-Sweep generates do not block on the writer queue.

    Returns:
        Quart response object
    """
    token = get_token_fn()
    if not token:
        return api_error("API token is not configured", 400,
                         hint="Set your NAI API token in Settings")

    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return api_error("prompt is required", 400)

    negative = (data.get("negative_prompt") or "").strip()

    # WC/DP expansion -- NAI does not interpret __wc__ or {a|b|c}, so always expand
    extra_wc = data.get("client_wildcards") if isinstance(data.get("client_wildcards"), dict) else None
    _seed = data.get("seed", -1)
    if not isinstance(_seed, int):
        _seed = -1
    expansion = maybe_expand_prompt(
        prompt, negative, True,
        seed=_seed if _seed not in (-1, None) else None,
        extra_wildcards=extra_wc)
    prompt = expansion["prompt"]
    negative = expansion["negative"]

    # Auto-convert SD-style syntax in expanded wildcards to NAI format.
    # The sd_nai_convert extension is optional; skip silently if not installed.
    if expansion["expanded"]:
        try:
            from importlib import import_module
            _engine = import_module(
                "extensions.builtin_sd_nai_convert.core_impl.sd_nai_convert_engine"
            )
            prompt = _engine.convert_sd_to_nai(prompt, strip_lora=True, strip_embedding=True)
            negative = _engine.convert_sd_to_nai(negative, strip_lora=True, strip_embedding=True)
            expansion["prompt"] = prompt
        except ImportError:
            logger.debug("sd_nai_convert extension not available; skipping SD→NAI syntax conversion")

    params: dict[str, Any] = {}
    _build_generate_params(data, params)
    _build_img2img_params(data, params)
    _build_reference_params(data, params)
    _build_character_params(data, params, _seed, extra_wc)

    emit(GEN_SUBMIT, {
        "bridge": _BRIDGE_TAG,
        "prompt_preview": prompt[:120],
        "params": params,
    }, source=_EXT_NAME)

    client = NAIClient(token)

    # V5 Opus Usage Limit guard: only applies to V5 models, and only to
    # requests that would actually draw from the free usage-limit tier
    # (normal resolution, <=28 steps) -- a higher-res/step V5 request always
    # costs Anlas regardless of the usage limit, so it is not gated here.
    if get_extension_config_value(_EXT_NAME, "block_anlas_on_v5_limit", False):
        model = params.get("model", MODELS[0])
        steps = params.get("steps", 28)
        width = params.get("width", 832)
        height = params.get("height", 1216)
        if model_generation(model) == GEN_V5 and is_opus_free_generation(width, height, steps):
            # Fail closed on a failed subscription fetch: the user opted
            # into this guard specifically to avoid spending Anlas, so a
            # check we cannot complete must not silently let a spend
            # through. Off the event loop via run_long_blocking_sync --
            # NAIClient.get_anlas() is a synchronous HTTP call (same
            # executor as client.generate() below).
            usage_result = await run_long_blocking_sync(client.get_anlas)
            # "ok" alone is not enough: a 200 response whose subscription
            # object has no "usage" block is just as unverifiable as a
            # failed request (e.g. NAI hasn't rolled the field out yet, or
            # the shape changed) -- both must block, not silently pass.
            if not usage_result.get("ok") or usage_result.get("usage") is None:
                return api_error(
                    "Could not verify NAI V5 usage limit; generation blocked to avoid an "
                    "unverified Anlas spend (disable the block-on-limit option in Settings "
                    "to allow generation without this check).",
                    502,
                    code="nai_usage_check_failed",
                )
            if NAIClient.usage_exhausted(usage_result.get("usage")):
                return api_error(
                    "NAI V5 usage limit exhausted; generation blocked to avoid spending Anlas "
                    "(disable the block-on-limit option in Settings to allow Anlas fallback).",
                    423,
                    code="nai_usage_limit_blocked",
                )

    t0 = time.time()
    # Long-blocking: NAI API call can take tens of seconds. Use the dedicated
    # executor so the default pool stays free for /api/files/thumbnails-batch.
    result = await run_long_blocking_sync(
        client.generate,
        prompt,
        negative,
        **params,
    )
    elapsed_ms = int((time.time() - t0) * 1000)

    if not result["ok"]:
        emit(GEN_ERROR, {
            "bridge": _BRIDGE_TAG,
            "error": result["error"],
        }, source=_EXT_NAME)
        return api_error(result["error"], 502)

    raw_images = result["images"]
    used_seed = result.get("seed", -1)
    image_format = params.get("image_format", "png")
    if image_format not in ("png", "webp", "jpg"):
        image_format = "png"

    # Convert format if needed (NAI API only returns png/webp natively)
    raw_images = await run_blocking_sync(
        _convert_images_if_needed,
        raw_images,
        image_format,
    )

    # Auto-save if configured (skip when client requests deferred batch save,
    # e.g. Sweep mode that batches everything at the end of the run).
    saved_paths: list[str] = []
    # When sweep_meta is present, indexing runs synchronously and we collect
    # (path, file_id) pairs so the Sweep client can quick-jump to each result.
    saved_items: list[dict] | None = None
    skip_save = bool(data.get("skip_save"))
    save_folder = get_extension_config_value(
        _EXT_NAME, "save_folder", "")
    auto_save = get_extension_config_value(
        _EXT_NAME, "auto_save", False)
    if not skip_save and save_folder and auto_save:
        saved_paths = await run_blocking_sync(
            save_images,
            raw_images,
            used_seed,
            save_folder,
            image_format=image_format,
            naming=get_extension_config_value(
                _EXT_NAME, "save_naming", "daily_folder"),
        )
        if saved_paths:
            sweep_meta = data.get("sweep_meta")
            if sweep_meta:
                from core.bridge_core.sweep_db import upsert_sweep_from_meta
                from core.bridge_core.sweep_xmp import write_sweep_xmp_to_paths
                await run_blocking_sync(write_sweep_xmp_to_paths, saved_paths, sweep_meta)
            if get_extension_config_value(_EXT_NAME, "auto_import", True):
                if sweep_meta:
                    # Sweep needs file_id back so the client can jump to
                    # each result; block until indexing finishes.
                    mapping = import_saved_files_sync(saved_paths)
                    saved_items = [
                        {"path": p, "file_id": mapping.get(p)}
                        for p in saved_paths
                    ]
                    for p in saved_paths:
                        upsert_sweep_from_meta(sweep_meta, mapping.get(p))
                else:
                    import_saved_files_async(saved_paths)
            elif sweep_meta:
                # auto_import off: still register the run header so /sweep
                # history lists it (file_id linkage stays NULL).
                upsert_sweep_from_meta(sweep_meta, None)
                # Return path info so client can display results even without file_id.
                saved_items = [{"path": p, "file_id": None} for p in saved_paths]

    images = []
    for img_bytes in raw_images:
        b64 = base64.b64encode(img_bytes).decode("ascii")
        images.append({"base64": b64, "seed": used_seed})

    emit(GEN_COMPLETE, {
        "bridge": _BRIDGE_TAG,
        "images_count": len(images),
        "elapsed_ms": elapsed_ms,
    }, source=_EXT_NAME)

    resp: dict[str, Any] = {
        "images": images,
        "elapsed_ms": elapsed_ms,
        "image_format": image_format,
    }
    resp["expanded_prompt"] = prompt  # always show final prompt
    if expansion["expanded"]:
        resp["original_prompt"] = expansion["original_prompt"]
    resp["final_negative"] = negative  # always include (may be empty string)
    if params.get("characters"):
        resp["characters"] = params["characters"]
    if saved_paths:
        resp["saved"] = saved_paths
    if saved_items is not None:
        resp["saved_items"] = saved_items
    return api_success(resp)


async def handle_save_batch(request_obj) -> tuple:
    """Batch-save a list of pre-generated NAI images (Sweep deferred-save)."""
    from core.bridge_core.bridge_save_batch import handle_save_batch as _handle
    return await _handle(request_obj, ext_name=_EXT_NAME, save_fn=save_images)
