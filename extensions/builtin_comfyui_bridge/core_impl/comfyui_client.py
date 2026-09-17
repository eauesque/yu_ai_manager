"""ComfyUI API client facade."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from core.bridge_core import BridgeConnectionError, BridgeHTTPClient, BridgeHTTPError

try:
    from .comfyui_client_discovery import (
        has_node,
        list_custom_nodes,
        list_embeddings,
        list_loras,
        list_required_enum,
        test_connection,
    )
    from .comfyui_client_upload import upload_image as upload_image_impl
    from .comfyui_client_wait import (
        connect_ws as _connect_ws_fn,
    )
    from .comfyui_client_wait import (
        get_images as _get_images_fn,
    )
    from .comfyui_client_wait import (
        get_output_paths as _get_output_paths_fn,
    )
    from .comfyui_client_wait import (
        wait_for_result_impl,
    )
except ImportError:  # pragma: no cover - top-level extension import path
    from comfyui_client_discovery import (
        has_node,
        list_custom_nodes,
        list_embeddings,
        list_loras,
        list_required_enum,
        test_connection,
    )
    from comfyui_client_upload import upload_image as upload_image_impl
    from comfyui_client_wait import (
        connect_ws as _connect_ws_fn,
    )
    from comfyui_client_wait import (
        get_images as _get_images_fn,
    )
    from comfyui_client_wait import (
        get_output_paths as _get_output_paths_fn,
    )
    from comfyui_client_wait import (
        wait_for_result_impl,
    )


class ComfyUIClient:
    def __init__(self, api_url: str, timeout: float = 30.0, backend_id: str | None = None) -> None:
        from .comfyui_api import _get_default_headers
        extra: dict[str, str] = {}
        if backend_id and backend_id != "__fallback__":
            extra["X-Backend-Id"] = backend_id
        self._http = BridgeHTTPClient(
            api_url,
            timeout=timeout,
            default_headers={**_get_default_headers(), **extra},
        )
        self.api_url = api_url.rstrip("/")
        self._backend_id = backend_id or "__fallback__"

    def test_connection(self) -> dict[str, Any]:
        return test_connection(self._http)

    def list_samplers(self) -> list[str]:
        return list_required_enum(self._http, "KSampler", "sampler_name")

    def list_schedulers(self) -> list[str]:
        return list_required_enum(self._http, "KSampler", "scheduler")

    def list_models(self) -> list[str]:
        return list_required_enum(self._http, "CheckpointLoaderSimple", "ckpt_name")

    def list_loras(self) -> list[str]:
        return list_loras(self._http)

    def list_embeddings(self) -> list[str]:
        return list_embeddings(self._http)

    def list_custom_nodes(self) -> list[dict[str, Any]]:
        return list_custom_nodes(self._http)

    def has_node(self, node_type: str) -> bool:
        return has_node(self._http, node_type)

    def list_models_by_loader(self, node_type: str, input_name: str) -> list[str]:
        return list_required_enum(self._http, node_type, input_name)

    def list_loader_options(self, node_type: str, input_name: str) -> list[str]:
        return list_required_enum(self._http, node_type, input_name)

    def list_diffusion_models(self) -> list[str]:
        return self.list_models_by_loader("UNETLoader", "unet_name")

    def list_text_encoders(self) -> list[str]:
        return self.list_models_by_loader("CLIPLoader", "clip_name")

    def list_clip_types(self) -> list[str]:
        types = self.list_loader_options("DualCLIPLoader", "type")
        return types or self.list_loader_options("CLIPLoader", "type")

    def list_weight_dtypes(self) -> list[str]:
        dtypes = self.list_loader_options("UNETLoader", "weight_dtype")
        return dtypes or ["default", "fp8_e4m3fn", "fp8_e4m3fn_fast", "fp8_e5m2", "fp16", "bf16", "fp32"]

    def list_controlnets(self) -> list[str]:
        return self.list_models_by_loader("ControlNetLoader", "control_net_name")

    def list_upscale_models(self) -> list[str]:
        return self.list_models_by_loader("UpscaleModelLoader", "model_name")

    def upload_image(self, image_bytes: bytes, filename: str) -> str:
        return upload_image_impl(self.api_url, image_bytes, filename)

    def queue_prompt(self, workflow: dict, client_id: str) -> dict[str, Any]:
        return self._http.post_json("/prompt", {"prompt": workflow, "client_id": client_id}, timeout=15)

    def connect_ws(self, client_id: str):
        return _connect_ws_fn(self.api_url, client_id, backend_id=self._backend_id)

    def wait_for_result(
        self,
        prompt_id: str,
        client_id: str,
        *,
        on_progress: Callable[[int, int], None] | None = None,
        timeout: float = 300.0,
        pre_ws=None,
    ) -> dict[str, Any]:
        return wait_for_result_impl(
            self._http,
            self.api_url,
            prompt_id,
            client_id,
            on_progress=on_progress,
            timeout=timeout,
            pre_ws=pre_ws,
            backend_id=self._backend_id,
        )

    def get_images(self, prompt_id: str) -> list[dict[str, Any]]:
        return _get_images_fn(self._http, prompt_id)

    def get_output_paths(self, prompt_id: str) -> list[dict[str, str]]:
        return _get_output_paths_fn(self._http, prompt_id)

    def refresh_assets(self) -> dict[str, Any]:
        """Re-fetch /object_info for the loader nodes so ComfyUI's internal
        mtime-based cache rebuilds and picks up newly-added files on disk.

        ComfyUI doesn't expose a direct "refresh" endpoint like SD WebUI's
        ``/sdapi/v1/refresh-checkpoints``; instead, calling
        ``/object_info/<NodeType>`` triggers ``folder_paths.get_filename_list_``
        which checks the search-path directory mtimes and rebuilds the cache
        when something on disk changed. We hit one representative loader per
        category so the most common dropdowns refresh in one click.

        Returns ``{category: {ok, count} | {ok: False, error}}``.
        """
        loaders = [
            ("checkpoints",   "CheckpointLoaderSimple", "ckpt_name"),
            ("loras",         "LoraLoader",             "lora_name"),
            ("vae",           "VAELoader",              "vae_name"),
            ("clip",          "CLIPLoader",             "clip_name"),
            ("unet",          "UNETLoader",             "unet_name"),
            ("controlnet",    "ControlNetLoader",       "control_net_name"),
            ("upscale_model", "UpscaleModelLoader",     "model_name"),
        ]
        results: dict[str, Any] = {}
        for label, node_type, field in loaders:
            try:
                data = self._http.get(f"/object_info/{node_type}", timeout=30)
                inputs = data.get(node_type, {}).get("input", {}).get("required", {})
                names = list(inputs.get(field, [[]])[0])
                results[label] = {"ok": True, "count": len(names)}
            except Exception as exc:  # noqa: BLE001
                # Loader missing on this install (e.g. CLIPLoader on early
                # ComfyUI versions) is not an error — just report skipped.
                results[label] = {"ok": False, "error": str(exc)}
        return results

    def interrupt(self) -> bool:
        try:
            self._http.post_json("/interrupt", {}, timeout=5)
            return True
        except (BridgeConnectionError, BridgeHTTPError):
            return False

    @staticmethod
    def new_client_id() -> str:
        return uuid.uuid4().hex[:16]
