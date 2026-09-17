"""Generation helpers for the classic SD WebUI API client."""

from __future__ import annotations


def switch_model(http, checkpoint: str) -> dict:
    """Switch the active checkpoint model."""
    try:
        http.post_json("/sdapi/v1/options", {"sd_model_checkpoint": checkpoint}, timeout=120)
        return {"ok": True, "model": checkpoint}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def txt2img(
    http,
    prompt: str,
    negative_prompt: str = "",
    *,
    steps: int = 28,
    sampler_name: str = "Euler a",
    cfg_scale: float = 7.0,
    width: int = 512,
    height: int = 768,
    seed: int = -1,
    extra: dict | None = None,
) -> dict:
    body = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "steps": steps,
        "sampler_name": sampler_name,
        "cfg_scale": cfg_scale,
        "width": width,
        "height": height,
        "seed": seed,
    }
    if extra:
        body.update(extra)
    return http.post_json("/sdapi/v1/txt2img", body, timeout=max(http.timeout, 120))


def img2img(
    http,
    prompt: str,
    negative_prompt: str = "",
    *,
    init_images,
    denoising_strength: float = 0.75,
    steps: int = 28,
    sampler_name: str = "Euler a",
    cfg_scale: float = 7.0,
    width: int = 512,
    height: int = 768,
    seed: int = -1,
    extra: dict | None = None,
) -> dict:
    body = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "init_images": list(init_images),
        "denoising_strength": denoising_strength,
        "steps": steps,
        "sampler_name": sampler_name,
        "cfg_scale": cfg_scale,
        "width": width,
        "height": height,
        "seed": seed,
    }
    if extra:
        body.update(extra)
    return http.post_json("/sdapi/v1/img2img", body, timeout=max(http.timeout, 120))
