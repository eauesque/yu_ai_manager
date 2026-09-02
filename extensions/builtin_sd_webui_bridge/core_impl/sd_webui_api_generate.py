"""SD WebUI Bridge generate endpoint logic."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from core.extensions_core.extensions_admin import get_extension_config_value

from core.bridge_core import BridgeConnectionError, BridgeHTTPError
from core.bridge_core.bridge_import import (
    import_saved_files_sync,
)
from core.bridge_core.prompt_expand import maybe_expand_prompt
from core.event_bus import emit
from core.event_bus.event_types import GEN_COMPLETE, GEN_ERROR, GEN_SUBMIT
from core.infra_core.api_errors import api_error, api_success
from core.infra_core.blocking_tasks import run_blocking_sync, run_long_blocking_sync

from . import sd_webui_generate_helpers as _generate_helpers

_auto_save_images = _generate_helpers.auto_save_images
_build_extra_params = _generate_helpers.build_extra_params
_convert_images_if_needed = _generate_helpers.convert_images_if_needed
_extract_adetailer_info = _generate_helpers.extract_adetailer_info
_reset_save_suppression_cache = _generate_helpers.reset_save_suppression_cache
_save_suppressed_urls = _generate_helpers.save_suppressed_urls
_suppress_save_once = _generate_helpers.suppress_save_once

logger = logging.getLogger(__name__)

_EXT_NAME = "builtin-sd-webui-bridge"
_BRIDGE_TAG = "sd-webui"


def _run_progress_poller(task_id: str, client, stop_event: threading.Event) -> None:
    """Background thread: polls SD WebUI progress and writes to task_registry."""
    from core.bridge_core import task_registry as _tr
    while not stop_event.wait(1.0):
        try:
            prog = client.get_progress()
            progress = prog.get("progress", 0)
            step = prog.get("state", {}).get("sampling_step", 0)
            total = prog.get("state", {}).get("sampling_steps", 0)
            _tr.update_progress(task_id, int(progress * 100), step, total)
        except Exception:
            logger.debug("progress poll failed", exc_info=True)

async def handle_generate(data: dict, make_client_fn) -> tuple:
    """Handle the /api/generate endpoint logic.

    Sweep contract: when the request includes ``sweep_meta``, save indexing
    blocks until completion and the response includes
    ``saved_items: [{path, file_id}, ...]``. Without ``sweep_meta``, indexing
    is fire-and-forget so non-Sweep generates do not block on the writer queue.

    Returns:
        Quart response object
    """
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return api_error("prompt is required", 400)

    negative = (data.get("negative_prompt") or "").strip()

    # WC/DP expansion
    expand_wc = bool(data.get("expand_wildcards", False))
    extra_wc = data.get("client_wildcards") if isinstance(data.get("client_wildcards"), dict) else None
    _seed = data.get("seed", -1)
    expansion = maybe_expand_prompt(
        prompt, negative, expand_wc,
        seed=_seed if _seed not in (-1, None) else None,
        extra_wildcards=extra_wc)
    prompt = expansion["prompt"]
    negative = expansion["negative"]

    # Auto-convert NAI-style syntax in expanded wildcards to SD format
    if expansion["expanded"]:
        from importlib import import_module
        _engine = import_module("extensions.builtin_sd_nai_convert.core_impl.sd_nai_convert_engine")
        prompt = _engine.convert_nai_to_sd(prompt)
        negative = _engine.convert_nai_to_sd(negative)
        expansion["prompt"] = prompt

    def _clamp_int(val: Any, default: int, lo: int, hi: int) -> int:
        try:
            return max(lo, min(int(val), hi))
        except (ValueError, TypeError):
            return default

    params: dict[str, Any] = {
        "steps": _clamp_int(data.get("steps", 28), 28, 1, 200),
        "sampler_name": data.get("sampler_name", "Euler a"),
        "cfg_scale": max(0.0, min(float(data.get("cfg_scale", 7.0)), 30.0)),
        "width": _clamp_int(data.get("width", 512), 512, 64, 16384),
        "height": _clamp_int(data.get("height", 768), 768, 64, 16384),
        "seed": _clamp_int(data.get("seed", -1), -1, -1, 2**32 - 1),
    }

    image_format = (data.get("image_format") or "png").strip().lower()
    if image_format not in ("png", "webp", "jpg"):
        image_format = "png"
    extra = _build_extra_params(data)

    # batch_size: pass through to SD WebUI API so each call generates N images.
    # Clamp to max_batch_size config to prevent VRAM overload.
    _max_batch_size = get_extension_config_value(_EXT_NAME, "max_batch_size", 8)
    _batch_size = _clamp_int(data.get("batch_size", 1), 1, 1, _max_batch_size)
    if _batch_size > 1:
        extra = dict(extra)
        extra["batch_size"] = _batch_size

    # Bridge-managed save: tell SD WebUI not to save anything to its own
    # outdir, take responsibility for saving via _auto_save_images so that
    # sweep XMP can be embedded into the file (we cannot reach SD WebUI's
    # own saved files). Validate save_folder up-front so the user does not
    # silently lose generated images.
    bridge_managed = bool(get_extension_config_value(
        _EXT_NAME, "bridge_managed_save", False))
    if bridge_managed:
        save_folder_cfg = get_extension_config_value(_EXT_NAME, "save_folder", "")
        if not save_folder_cfg:
            return api_error(
                "Bridge-managed save is on but save_folder is empty — "
                "set the save folder in this bridge's settings or turn off "
                "Bridge-managed save.",
                400,
            )
        extra = dict(extra) if extra else {}
        extra["do_not_save_samples"] = True
        extra["do_not_save_grid"] = True

    if extra:
        params["extra"] = extra

    # img2img detection
    init_images_raw = data.get("init_images")
    is_img2img = bool(
        init_images_raw
        and isinstance(init_images_raw, list)
        and init_images_raw
    )

    emit(GEN_SUBMIT, {
        "bridge": _BRIDGE_TAG,
        "mode": "img2img" if is_img2img else "txt2img",
        "prompt_preview": prompt[:120],
        "params": params,
    }, source=_EXT_NAME)

    try:
        client = make_client_fn()
    except Exception:
        logger.exception("Failed to create SD WebUI client")
        return api_error("SD WebUI connection failed", 502)

    # Globally suppress save on the upstream when bridge-managed save is on.
    # Belt-and-suspenders alongside the per-request do_not_save_samples/grid
    # flags above: needed for Gradio 4 Forge (drops per-request keys) and
    # also for classic-SDAPI forks observed to ignore them. Idempotent on
    # forks that already honour per-request flags.
    if bridge_managed:
        _suppress_save_once(client)

    t0 = time.time()

    task_id: str | None = data.get("task_id")
    _stop_poll = threading.Event()
    # Always stop the poller on any exit path, including future early-returns
    # added between poller-start and the generation block.
    try:
        if task_id:
            threading.Thread(
                target=_run_progress_poller,
                args=(task_id, client, _stop_poll),
                daemon=True,
            ).start()

        try:
            # Long-blocking: SD WebUI generation can take tens of seconds.
            # Use the dedicated executor so default-pool consumers (e.g. /api/files/
            # thumbnails-batch) are not starved while generation is in flight.
            if is_img2img:
                denoising = float(data.get("denoising_strength", 0.75))
                raw = await run_long_blocking_sync(
                    client.img2img,
                    prompt,
                    negative,
                    init_images=init_images_raw,
                    denoising_strength=denoising,
                    **params,
                )
            else:
                raw = await run_long_blocking_sync(
                    client.txt2img,
                    prompt,
                    negative,
                    **params,
                )
        except BridgeConnectionError as exc:
            emit(GEN_ERROR, {
                "bridge": _BRIDGE_TAG, "error": str(exc),
            }, source=_EXT_NAME)
            logger.warning("SD WebUI generation connection error: %s", exc)
            return api_error("SD WebUI request failed", 502)
        except BridgeHTTPError as exc:
            emit(GEN_ERROR, {
                "bridge": _BRIDGE_TAG, "error": f"HTTP {exc.status}",
            }, source=_EXT_NAME)
            return api_error(f"SD WebUI error: HTTP {exc.status}", 502)
    finally:
        _stop_poll.set()

    elapsed_ms = int((time.time() - t0) * 1000)

    images_raw = raw.get("images", [])
    info = raw.get("parameters", {})
    used_seed = info.get("seed", -1)

    # Convert format if needed (SD WebUI always returns PNG)
    images_raw = await run_blocking_sync(
        _convert_images_if_needed,
        images_raw,
        image_format,
    )

    images = []
    for img_b64 in images_raw:
        images.append({"base64": img_b64, "seed": used_seed})

    skip_save = bool(data.get("skip_save"))
    sweep_meta = data.get("sweep_meta")
    # When sweep_meta is present, indexing runs synchronously and we collect
    # (path, file_id) pairs so the Sweep client can quick-jump to each result.
    saved_items: list[dict] | None = None
    saved_paths = [] if skip_save else await run_blocking_sync(
        _auto_save_images,
        images_raw,
        used_seed,
        image_format=image_format,
        force_save=bridge_managed,
        skip_import=bool(sweep_meta),
    )
    if saved_paths and sweep_meta:
        from core.bridge_core.sweep_db import upsert_sweep_from_meta
        from core.bridge_core.sweep_xmp import write_sweep_xmp_to_paths
        await run_blocking_sync(write_sweep_xmp_to_paths, saved_paths, sweep_meta)
        if get_extension_config_value(_EXT_NAME, "auto_import", True):
            # Sweep needs file_id back so the client can jump to
            # each result; block until indexing finishes.
            mapping = await run_blocking_sync(import_saved_files_sync, saved_paths)
            saved_items = [
                {"path": p, "file_id": mapping.get(p)}
                for p in saved_paths
            ]
            for p in saved_paths:
                upsert_sweep_from_meta(sweep_meta, mapping.get(p))
        else:
            # auto_import off: still register the run header so /sweep
            # history lists it (file_id linkage stays NULL).
            upsert_sweep_from_meta(sweep_meta, None)

    emit(GEN_COMPLETE, {
        "bridge": _BRIDGE_TAG,
        "images_count": len(images),
        "elapsed_ms": elapsed_ms,
    }, source=_EXT_NAME)

    resp: dict = {
        "images": images,
        "elapsed_ms": elapsed_ms,
        "image_format": image_format,
    }
    resp["expanded_prompt"] = prompt  # always show the final prompt
    if expansion["expanded"]:
        resp["original_prompt"] = expansion["original_prompt"]
    resp["final_negative"] = negative  # always include (may be empty string)
    adetailer_info = _extract_adetailer_info(data)
    if adetailer_info:
        resp["adetailer"] = adetailer_info
    if saved_paths:
        resp["saved"] = saved_paths
    if saved_items is not None:
        resp["saved_items"] = saved_items
    return api_success(resp)
