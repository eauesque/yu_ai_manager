"""Gradio 4 (Forge new) client for SD WebUI Bridge.

Forge's new main branch uses Gradio 4.x and exposes generation
via ``POST /call/{api_name}`` + SSE instead of ``/sdapi/v1/``.
This client provides the same public interface as :class:`SDWebUIClient`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from core.bridge_core import BridgeConnectionError, BridgeHTTPClient, BridgeHTTPError

from .gradio4_cache import ensure_txt2img_schema, get_config, get_info
from .gradio4_generation import fetch_file_as_b64
from .gradio4_generation_ops import get_progress, img2img, interrupt, txt2img
from .gradio4_queries import (
    list_models,
    list_samplers,
    list_upscalers,
    set_save_options,
    switch_model,
    test_connection,
)


class Gradio4ForgeClient:
    """Client for Forge (Gradio 4.x) that mirrors :class:`SDWebUIClient` API.

    Uses ``/call/{api_name}`` (async queue) + SSE for generation, and
    ``/config`` to discover component defaults.
    """

    api_type = "gradio4"

    def __init__(
        self,
        api_url: str,
        timeout: float = 30.0,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        from .sd_webui_api import _get_default_headers
        default_headers = _get_default_headers()
        if extra_headers:
            default_headers = {**default_headers, **extra_headers}
        self._http = BridgeHTTPClient(api_url, timeout=timeout,
                                      default_headers=default_headers)
        self.api_url = api_url.rstrip("/")

        # Cached schema/config data (populated on first use)
        self._info_cache: dict | None = None
        self._config_cache: dict | None = None
        self._txt2img_label_map: dict[str, int] | None = None
        self._txt2img_defaults: list[Any] | None = None

    # -- schema/config cache --------------------------------------------

    def _get_info(self) -> dict:
        return get_info(self)

    def _get_config(self) -> dict:
        return get_config(self)

    def _ensure_txt2img_schema(self) -> None:
        ensure_txt2img_schema(self)

    # -- connection -----------------------------------------------------

    def test_connection(self) -> dict[str, Any]:
        return test_connection(self)

    # -- queries --------------------------------------------------------

    def list_samplers(self) -> list[str]:
        return list_samplers(self)

    def list_models(self) -> list[str]:
        return list_models(self)

    def switch_model(self, checkpoint: str) -> dict[str, Any]:
        return switch_model(self, checkpoint)

    def refresh_assets(self) -> dict[str, Any]:
        """Best-effort rescan via /sdapi/v1/* if available on this fork.

        Gradio4-only forks may not expose these endpoints — failures are
        captured per-asset rather than raised so the UI shows partial
        results when only some endpoints exist.
        """
        results: dict[str, Any] = {}
        endpoints = [
            ("checkpoints", "/sdapi/v1/refresh-checkpoints"),
            ("vae",         "/sdapi/v1/refresh-vae"),
            ("loras",       "/sdapi/v1/refresh-loras"),
        ]
        for label, ep in endpoints:
            try:
                self._http.post_json(ep, {}, timeout=60)
                results[label] = {"ok": True}
            except Exception as exc:  # noqa: BLE001
                results[label] = {"ok": False, "error": str(exc)}
        return results

    def list_upscalers(self) -> list[str]:
        return list_upscalers(self)

    def set_save_options(
        self, *, samples_save: bool, grid_save: bool
    ) -> tuple[bool, str | None]:
        return set_save_options(
            self, samples_save=samples_save, grid_save=grid_save
        )

    # -- discovery (limited on Gradio 4) --------------------------------

    def list_loras(self) -> list[dict[str, Any]]:
        """Return LoRA list. Uses /sdapi/v1/loras if available."""
        try:
            data = self._http.get("/sdapi/v1/loras")
            if isinstance(data, list):
                return [
                    {
                        "name": item.get("name", ""),
                        "alias": item.get("alias", ""),
                        "path": item.get("path", ""),
                    }
                    for item in data
                    if isinstance(item, dict)
                ]
        except (BridgeConnectionError, BridgeHTTPError):
            pass
        return []

    def list_embeddings(self) -> dict[str, list[str]]:
        return {"loaded": [], "skipped": []}

    def list_scripts(self) -> dict[str, list[str]]:
        return {"txt2img": [], "img2img": []}

    def list_script_info(self) -> list[dict[str, Any]]:
        return []

    def list_extensions(self) -> list[dict[str, Any]]:
        return []

    # -- generation -----------------------------------------------------

    def txt2img(
        self,
        prompt: str,
        negative_prompt: str = "",
        *,
        steps: int = 28,
        sampler_name: str = "Euler a",
        cfg_scale: float = 7.0,
        width: int = 512,
        height: int = 768,
        seed: int = -1,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return txt2img(
            self,
            prompt,
            negative_prompt,
            steps=steps,
            sampler_name=sampler_name,
            cfg_scale=cfg_scale,
            width=width,
            height=height,
            seed=seed,
            extra=extra,
        )

    def img2img(
        self,
        prompt: str,
        negative_prompt: str = "",
        *,
        init_images: Sequence[str],
        denoising_strength: float = 0.75,
        steps: int = 28,
        sampler_name: str = "Euler a",
        cfg_scale: float = 7.0,
        width: int = 512,
        height: int = 768,
        seed: int = -1,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return img2img(
            self,
            prompt,
            negative_prompt,
            init_images=init_images,
            denoising_strength=denoising_strength,
            steps=steps,
            sampler_name=sampler_name,
            cfg_scale=cfg_scale,
            width=width,
            height=height,
            seed=seed,
            extra=extra,
        )

    # -- progress / cancel ----------------------------------------------

    def get_progress(self) -> dict[str, Any]:
        return get_progress(self)

    def interrupt(self) -> bool:
        return interrupt(self)

    def _fetch_file_as_b64(self, url: str) -> str | None:
        """Fetch a file from Forge's file server and return as base64."""
        return fetch_file_as_b64(self.api_url, url)
