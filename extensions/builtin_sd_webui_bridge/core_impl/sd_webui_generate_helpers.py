"""Helper functions for SD WebUI generate endpoint."""

from __future__ import annotations

import logging
from typing import Any

from core.extensions_core.extensions_admin import get_extension_config_value

from core.bridge_core.bridge_import import import_saved_files_async
from core.bridge_core.bridge_save import save_images as bridge_save_images

logger = logging.getLogger(__name__)

EXT_NAME = "builtin-sd-webui-bridge"
save_suppressed_urls: set[str] = set()


def reset_save_suppression_cache() -> None:
    save_suppressed_urls.clear()


def suppress_save_once(client) -> None:
    api_url = getattr(client, "api_url", None)
    if not api_url or api_url in save_suppressed_urls:
        return
    setter = getattr(client, "set_save_options", None)
    if setter is None:
        return
    ok, err = setter(samples_save=False, grid_save=False)
    api_type = getattr(client, "api_type", "?")
    if ok:
        save_suppressed_urls.add(api_url)
        logger.info("SD WebUI save suppression applied (api_type=%s): %s", api_type, api_url)
    else:
        logger.warning(
            "SD WebUI save suppression failed for %s (api_type=%s): %s — "
            "upstream may continue saving to its own outdir.",
            api_url, api_type, err,
        )


def extract_adetailer_info(data: dict) -> list:
    alwayson = data.get("alwayson_scripts")
    if not isinstance(alwayson, dict):
        return []
    ad_args = alwayson.get("ADetailer", {}).get("args", [])
    if not ad_args or ad_args[0] is not True:
        return []
    result = []
    for item in ad_args:
        if not isinstance(item, dict):
            continue
        model = item.get("ad_model", "")
        ad_prompt = item.get("ad_prompt", "")
        ad_negative = item.get("ad_negative_prompt", "")
        if model or ad_prompt or ad_negative:
            result.append({"model": model, "prompt": ad_prompt, "negative": ad_negative})
    return result


def build_extra_params(data: dict) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    alwayson = data.get("alwayson_scripts")
    if isinstance(alwayson, dict):
        extra["alwayson_scripts"] = alwayson
    if data.get("enable_hr"):
        _add_hires_params(extra, data)
    refiner_checkpoint = data.get("refiner_checkpoint")
    if refiner_checkpoint and isinstance(refiner_checkpoint, str) and refiner_checkpoint.strip():
        extra["refiner_checkpoint"] = refiner_checkpoint.strip()
        switch_at = data.get("refiner_switch_at")
        if switch_at is not None:
            try:
                extra["refiner_switch_at"] = max(0.0, min(1.0, float(switch_at)))
            except (ValueError, TypeError):
                extra["refiner_switch_at"] = 0.8
    return extra


def _add_hires_params(extra: dict[str, Any], data: dict) -> None:
    extra["enable_hr"] = True
    fields = {
        "hr_scale": (float, 2.0),
        "hr_upscaler": (str, "Latent"),
        "hr_second_pass_steps": (int, 0),
        "denoising_strength": (float, 0.7),
        "hr_resize_x": (int, 0),
        "hr_resize_y": (int, 0),
    }
    for field, (typ, default) in fields.items():
        val = data.get(field)
        if val is None:
            continue
        try:
            extra[field] = typ(val)
        except (ValueError, TypeError):
            extra[field] = default


def auto_save_images(
    images_raw: list,
    used_seed: int,
    image_format: str = "png",
    *,
    force_save: bool = False,
    skip_import: bool = False,
) -> list[str]:
    save_folder = get_extension_config_value(EXT_NAME, "save_folder", "")
    auto_save = get_extension_config_value(EXT_NAME, "auto_save", False)
    if not save_folder or not images_raw or (not auto_save and not force_save):
        return []
    import base64 as b64mod

    raw_bytes = []
    for b64str in images_raw:
        try:
            raw_bytes.append(b64mod.b64decode(b64str))
        except Exception as exc:
            logger.warning("auto_save_images: skipping malformed base64 entry: %s", exc)
    if len(raw_bytes) < len(images_raw):
        logger.warning(
            "auto_save_images: %d of %d images had invalid base64 and were skipped",
            len(images_raw) - len(raw_bytes), len(images_raw),
        )
    if not raw_bytes:
        return []
    saved_paths = bridge_save_images(
        raw_bytes,
        used_seed,
        save_folder,
        image_format=image_format,
        naming=get_extension_config_value(EXT_NAME, "save_naming", "daily_folder"),
    )
    if saved_paths and not skip_import and get_extension_config_value(EXT_NAME, "auto_import", True):
        import_saved_files_async(saved_paths)
    return saved_paths


def convert_images_if_needed(images_raw: list[str], image_format: str) -> list[str]:
    if image_format == "png" or not images_raw:
        return images_raw
    import base64 as b64mod

    from core.bridge_core.bridge_save import _convert_image

    converted_raw = []
    for b64str in images_raw:
        try:
            raw_bytes = b64mod.b64decode(b64str)
            raw_bytes = _convert_image(raw_bytes, image_format)
            converted_raw.append(b64mod.b64encode(raw_bytes).decode("ascii"))
        except Exception:
            converted_raw.append(b64str)
    return converted_raw
