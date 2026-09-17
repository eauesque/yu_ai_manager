import logging
from collections.abc import Sequence
from typing import Any

from core.bridge_core import BridgeConnectionError, BridgeHTTPError

from .gradio4_cache import ensure_txt2img_schema
from .gradio4_generation import build_txt2img_args, normalize_response
from .gradio4_io import call_gradio_and_wait

logger = logging.getLogger(__name__)


def txt2img(client, prompt: str, negative_prompt: str = "", *, steps: int = 28, sampler_name: str = "Euler a", cfg_scale: float = 7.0, width: int = 512, height: int = 768, seed: int = -1, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    ensure_txt2img_schema(client)
    args = build_txt2img_args(client._txt2img_defaults or [], client._txt2img_label_map or {}, prompt, negative_prompt, steps, sampler_name, cfg_scale, width, height, seed, extra)
    result_data = call_gradio_and_wait(client.api_url, "/txt2img", args, timeout=max(client._http.timeout, 120))
    return normalize_response(client.api_url, result_data, prompt, negative_prompt, seed)


def img2img(client, prompt: str, negative_prompt: str = "", *, init_images: Sequence[str], denoising_strength: float = 0.75, steps: int = 28, sampler_name: str = "Euler a", cfg_scale: float = 7.0, width: int = 512, height: int = 768, seed: int = -1, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    # init_images is not passed to the Gradio 4 endpoint — raise a clear error
    # rather than silently producing a txt2img result that looks like success.
    raise BridgeHTTPError(501, "img2img with init_images is not yet supported on Gradio 4 / Forge")


def get_progress(client) -> dict[str, Any]:
    try:
        data = client._http.get("/internal/progress", timeout=5)
        return {
            "progress": data.get("progress", 0),
            "eta_relative": data.get("eta", 0),
            "state": {"sampling_step": data.get("current", 0), "sampling_steps": data.get("total", 0)},
        }
    except (BridgeConnectionError, BridgeHTTPError):
        return {"progress": 0, "eta_relative": 0, "state": {}}


def interrupt(client) -> bool:
    try:
        client._http.post_json("/cancel", {}, timeout=5)
        return True
    except (BridgeConnectionError, BridgeHTTPError) as exc:
        logger.warning("interrupt failed: %s", exc)
        return False
