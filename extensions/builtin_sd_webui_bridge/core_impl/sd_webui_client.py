"""SD WebUI / Forge API client built on :class:`BridgeHTTPClient`.

Supports both the classic ``/sdapi/v1/`` API and Forge's Gradio 4 API.
Use :func:`detect_api_type` or :func:`create_client` to auto-detect.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .gradio4_client import Gradio4ForgeClient

from core.bridge_core import BridgeConnectionError, BridgeHTTPClient, BridgeHTTPError

from .sd_webui_generation import img2img as _img2img_impl
from .sd_webui_generation import switch_model as _switch_model_impl
from .sd_webui_generation import txt2img as _txt2img_impl
from .sd_webui_queries import (
    get_progress as _get_progress_impl,
)
from .sd_webui_queries import (
    interrupt as _interrupt_impl,
)
from .sd_webui_queries import (
    list_embeddings as _list_embeddings_impl,
)
from .sd_webui_queries import (
    list_extensions as _list_extensions_impl,
)
from .sd_webui_queries import (
    list_loras as _list_loras_impl,
)
from .sd_webui_queries import (
    list_names as _list_names_impl,
)
from .sd_webui_queries import (
    list_script_info as _list_script_info_impl,
)
from .sd_webui_queries import (
    list_scripts as _list_scripts_impl,
)
from .sd_webui_queries import (
    test_connection as _test_connection_impl,
)

logger = logging.getLogger(__name__)

# API type constants
API_SDAPI_V1 = "sdapi_v1"
API_GRADIO4 = "gradio4"


def detect_api_type(
    api_url: str,
    timeout: float = 5.0,
    *,
    extra_headers: dict[str, str] | None = None,
) -> str:
    """Detect whether the target uses classic sdapi or Gradio 4.

    Returns :data:`API_SDAPI_V1` or :data:`API_GRADIO4`.
    Raises :class:`BridgeConnectionError` if unreachable.
    """
    from .sd_webui_api import _get_default_headers
    default_headers = _get_default_headers()
    if extra_headers:
        default_headers = {**default_headers, **extra_headers}
    http = BridgeHTTPClient(api_url, timeout=timeout,
                            default_headers=default_headers)

    # Try classic sdapi first
    try:
        http.get("/sdapi/v1/options", timeout=timeout)
        return API_SDAPI_V1
    except BridgeHTTPError as exc:
        if exc.status != 404:
            # Non-404 error (auth etc.) -- assume sdapi is present
            return API_SDAPI_V1
    except BridgeConnectionError:
        raise

    # sdapi returned 404 -- try Gradio 4 ping
    try:
        http.get("/internal/ping", timeout=timeout)
        return API_GRADIO4
    except BridgeHTTPError:
        # /internal/ping exists but returned error -- still Gradio 4
        return API_GRADIO4
    except BridgeConnectionError:
        raise


def create_client(
    api_url: str,
    timeout: float = 30.0,
    *,
    extra_headers: dict[str, str] | None = None,
) -> SDWebUIClient | Gradio4ForgeClient:
    """Create the appropriate client based on auto-detection.

    Returns either :class:`SDWebUIClient` or :class:`Gradio4ForgeClient`.
    """
    api_type = detect_api_type(api_url, timeout=min(timeout, 10.0), extra_headers=extra_headers)
    if api_type == API_GRADIO4:
        from .gradio4_client import Gradio4ForgeClient
        return Gradio4ForgeClient(api_url, timeout=timeout, extra_headers=extra_headers)
    return SDWebUIClient(api_url, timeout=timeout, extra_headers=extra_headers)


class SDWebUIClient:
    """High-level wrapper around the SD WebUI ``--api`` endpoints.

    Parameters
    ----------
    api_url:
        Root URL of the SD WebUI instance (e.g. ``http://127.0.0.1:7860``).
    timeout:
        Default timeout in seconds.  ``txt2img`` uses a longer timeout.
    """

    # Identifies this client type
    api_type = "sdapi_v1"

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
        self.api_url = api_url

    # -- connection -------------------------------------------------

    def test_connection(self) -> dict[str, Any]:
        return _test_connection_impl(self._http)

    # -- queries ----------------------------------------------------

    def list_samplers(self) -> list[str]:
        return _list_names_impl(self._http, "/sdapi/v1/samplers", logger, "name")

    def list_models(self) -> list[str]:
        return _list_names_impl(self._http, "/sdapi/v1/sd-models", logger, "title")

    def switch_model(self, checkpoint: str) -> dict[str, Any]:
        return _switch_model_impl(self._http, checkpoint)

    def refresh_assets(self) -> dict[str, Any]:
        """Tell SD WebUI to rescan its checkpoints / VAEs / LoRAs.

        Useful after the user adds new model files to disk while the SD WebUI
        process is still running — without this the API returns the stale
        in-memory list. Each endpoint is wrapped individually because not all
        forks support every endpoint (vanilla SD WebUI lacks ``refresh-loras``;
        Forge has it). Returns a per-endpoint summary so the UI can report
        which kinds were actually refreshed.
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
        return _list_names_impl(self._http, "/sdapi/v1/upscalers", logger, "name")

    # -- discovery --------------------------------------------------

    def list_loras(self) -> list[dict[str, Any]]:
        return _list_loras_impl(self._http, logger)

    def list_embeddings(self) -> dict[str, list[str]]:
        return _list_embeddings_impl(self._http, logger)

    def list_scripts(self) -> dict[str, list[str]]:
        return _list_scripts_impl(self._http, logger)

    def list_script_info(self) -> list[dict[str, Any]]:
        return _list_script_info_impl(self._http, logger)

    def list_extensions(self) -> list[dict[str, Any]]:
        return _list_extensions_impl(self._http, logger)

    def set_save_options(
        self, *, samples_save: bool, grid_save: bool
    ) -> tuple[bool, str | None]:
        """Persistently flip the WebUI's global samples_save / grid_save.

        Defence in depth alongside the per-request ``do_not_save_samples`` /
        ``do_not_save_grid`` flags: some Forge forks silently ignore the
        per-request flags, so the bridge also disables save at the global
        options level when bridge-managed save is on. Idempotent and
        harmless even when per-request flags already work.
        """
        try:
            self._http.post_json(
                "/sdapi/v1/options",
                {"samples_save": samples_save, "grid_save": grid_save},
                timeout=30,
            )
            return True, None
        except BridgeHTTPError as exc:
            return False, f"HTTP {exc.status}"
        except BridgeConnectionError as exc:
            return False, str(exc)

    # -- generation -------------------------------------------------

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
        """Submit a txt2img generation request.

        Returns the raw JSON response from SD WebUI which includes
        ``images`` (list of base64 strings) and ``parameters``.
        Raises :class:`BridgeConnectionError` or :class:`BridgeHTTPError`
        on failure.
        """
        return _txt2img_impl(
            self._http,
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
        """Submit an img2img generation request.

        Parameters
        ----------
        init_images:
            List of base64-encoded source images (A1111 API convention).
        denoising_strength:
            How much to change the input image (0.0 = none, 1.0 = full).

        Returns the raw JSON response (same shape as ``txt2img``).
        """
        return _img2img_impl(
            self._http,
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

    # -- progress / cancel ------------------------------------------

    def get_progress(self) -> dict[str, Any]:
        """Poll generation progress.

        Returns ``{"progress": 0.0-1.0, "eta_relative": ..., ...}``.
        """
        return _get_progress_impl(self._http)

    def interrupt(self) -> bool:
        """Send an interrupt (cancel) request. Returns True on success."""
        return _interrupt_impl(self._http, logger)
