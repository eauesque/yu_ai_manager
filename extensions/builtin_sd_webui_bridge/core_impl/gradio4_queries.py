from typing import Any

from core.bridge_core import BridgeConnectionError, BridgeHTTPError

from .gradio4_cache import get_info
from .gradio4_io import call_gradio_and_wait
from .gradio4_params import (
    extract_model_choices,
    extract_sampler_choices,
    extract_upscaler_choices,
)


def test_connection(client) -> dict[str, Any]:
    try:
        client._http.get("/internal/ping", timeout=5)
    except BridgeConnectionError as exc:
        return {"ok": False, "error": str(exc)}
    except BridgeHTTPError as exc:
        return {"ok": False, "error": f"HTTP {exc.status}"}
    models = extract_model_choices(get_info(client))
    current_model = models[0] if models else "unknown"
    return {"ok": True, "model": current_model, "version": "Forge (Gradio 4)", "api_type": "gradio4"}


def list_samplers(client) -> list[str]:
    samplers = extract_sampler_choices(get_info(client))
    return samplers or ["DPM++ 2M", "DPM++ SDE", "Euler", "Euler a"]


def list_models(client) -> list[str]:
    return extract_model_choices(get_info(client))


def switch_model(client, checkpoint: str) -> dict[str, Any]:
    """Switch the active checkpoint.

    Forge exposes several checkpoint-related endpoints, but only a subset
    actually triggers a real model reload:

    * ``POST /sdapi/v1/options`` with ``sd_model_checkpoint`` calls
      ``main_entry.checkpoint_change(v)`` → real reload. Only available
      when Forge is launched with ``--api``.
    * ``/call/button_set_checkpoint_change`` is a UI relay: it just returns
      ``(model, vae, opts.dumpjson())`` to update the dropdowns. The actual
      reload happens only when the resulting client-side dropdown ``change``
      event fires, which never happens over the API.
    * ``/call/checkpoint_change`` is the dropdown's ``.change`` handler
      itself (Gradio 4 exposes unnamed handlers under their Python function
      name). Calling it directly triggers the real reload.

    We try sdapi first (simpler, atomic), then fall back to ``/call/checkpoint_change``.
    """
    # Try sdapi/v1/options POST first — only works when Forge is launched with --api.
    try:
        client._http.post_json("/sdapi/v1/options", {"sd_model_checkpoint": checkpoint}, timeout=120)
        client._info_cache = None
        return {"ok": True, "model": checkpoint}
    except BridgeHTTPError as exc:
        if exc.status != 404:
            return {"ok": False, "error": f"HTTP {exc.status}: {exc.body[:200]}"}
        # 404 → --api not enabled, fall through to Gradio4 direct dropdown change handler.
    except BridgeConnectionError as exc:
        return {"ok": False, "error": str(exc)}

    # Gradio4 direct call to the ui_checkpoint dropdown's change handler.
    # This IS what actually reloads the model (see main_entry.py checkpoint_change).
    try:
        call_gradio_and_wait(
            client.api_url, "/checkpoint_change", [checkpoint], timeout=120
        )
        client._info_cache = None
        return {"ok": True, "model": checkpoint}
    except (BridgeConnectionError, BridgeHTTPError) as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "error": f"switch_model error: {exc}"}


def list_upscalers(client) -> list[str]:
    return extract_upscaler_choices(get_info(client))


def set_save_options(
    client, *, samples_save: bool, grid_save: bool
) -> tuple[bool, str | None]:
    """POST /sdapi/v1/options to flip Forge's persistent save toggles.

    Gradio 4 Forge has no per-request "do not save" knob — its txt2img
    component args don't expose ``do_not_save_samples`` / ``do_not_save_grid``,
    so the flags we set in :mod:`sd_webui_api_generate` are silently dropped
    by ``build_txt2img_args``. Forge still keeps ``/sdapi/v1/options`` though
    (when launched with ``--api``), and that endpoint accepts the global
    ``samples_save`` / ``grid_save`` toggles.
    """
    try:
        client._http.post_json(
            "/sdapi/v1/options",
            {"samples_save": samples_save, "grid_save": grid_save},
            timeout=30,
        )
        return True, None
    except BridgeHTTPError as exc:
        return False, f"HTTP {exc.status}"
    except BridgeConnectionError as exc:
        return False, str(exc)
