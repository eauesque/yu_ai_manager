"""Workflow execution helpers for the ComfyUI bridge."""

from __future__ import annotations

import base64 as b64mod
import contextlib
import logging
import time
from pathlib import Path
from typing import Any

from core.extensions_core.extensions_admin import get_extension_config_value

from core.bridge_core import BridgeConnectionError, BridgeHTTPError
from core.bridge_core.bridge_import import (
    import_saved_files_async,
    import_saved_files_sync,
)
from core.bridge_core.bridge_save import save_images as bridge_save_images
from core.event_bus import emit
from core.event_bus.event_types import GEN_COMPLETE, GEN_ERROR, GEN_PROGRESS
from core.infra_core.api_errors import api_error, api_success

try:
    from .comfyui_generate_convert import convert_images
except ImportError:  # pragma: no cover - top-level extension import path
    from comfyui_generate_convert import convert_images

logger = logging.getLogger(__name__)

EXT_NAME = "builtin-comfyui-bridge"
BRIDGE_TAG = "comfyui"


def _safe_relative_path(value: str, *, allow_empty: bool) -> str | None:
    if not isinstance(value, str) or "\x00" in value:
        return None
    normalized = value.replace("\\", "/")
    if not normalized:
        return "" if allow_empty else None
    if normalized.startswith("/") or normalized.startswith("//"):
        return None
    if len(normalized) >= 2 and normalized[1] == ":":
        return None
    parts = normalized.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return None
    return normalized


def resolve_comfy_output_path(root: str | Path, subfolder: str, filename: str) -> Path | None:
    """Resolve a ComfyUI history output descriptor under *root* safely."""
    safe_name = _safe_relative_path(filename, allow_empty=False)
    if safe_name is None or "/" in safe_name:
        return None
    safe_sub = _safe_relative_path(subfolder or "", allow_empty=True)
    if safe_sub is None:
        return None
    root_path = Path(root).expanduser().resolve()
    candidate = root_path / safe_name if not safe_sub else root_path / safe_sub / safe_name
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root_path)
    except (OSError, ValueError):
        return None
    if not resolved.exists():
        return None
    return resolved


def resolve_sweep_xmp_target() -> str:
    """Return the directory where Sweep XMP should be written.

    When `comfy_output_same_as_save_folder` is on, mirror save_folder so users
    don't have to keep two paths in sync. Otherwise use the explicit
    comfy_output_root. Defaults to True only for fresh installs (i.e. when
    no explicit comfy_output_root was set).
    """
    explicit = (get_extension_config_value(EXT_NAME, "comfy_output_root", "") or "").strip()
    same_as_save = bool(
        get_extension_config_value(
            EXT_NAME, "comfy_output_same_as_save_folder", not bool(explicit),
        )
    )
    if same_as_save:
        return (get_extension_config_value(EXT_NAME, "save_folder", "") or "").strip()
    return explicit


def reset_progress(progress_state: dict[str, Any]) -> None:
    # NOTE: progress_state is a single shared dict (bridge-level singleton).
    # It is NOT safe for concurrent generation requests — multiple simultaneous
    # calls will stomp each other's progress values. When task_id is present,
    # the per-task registry (_tr.update_progress) is the authoritative source;
    # progress_state writes are skipped in that path to avoid stale overwrites.
    progress_state.update({"progress": 0, "step": 0, "total_steps": 0, "status": "idle"})


def execute_workflow(
    workflow: dict,
    client,
    client_id: str,
    progress_state: dict[str, Any],
    image_format: str = "png",
    extra_fields: dict[str, Any] | None = None,
    sweep_meta: dict[str, Any] | None = None,
    task_id: str | None = None,
) -> Any:
    """Execute a ComfyUI workflow and return the generation result."""
    try:
        from core.infra_core.debug_log import dlog as _dlog
        _dlog(
            "comfyui_bridge",
            "execute_workflow.start",
            node_count=len(workflow),
            latent_nodes=[
                f"{k}:{v['class_type']}" for k, v in workflow.items()
                if "Latent" in v["class_type"] or v["class_type"] in ("EmptyLatentImage", "EmptySD3LatentImage")
            ],
            encode_nodes=[
                f"{k}:{v['class_type']}" for k, v in workflow.items()
                if "CLIPText" in v["class_type"] or "BNK_" in v["class_type"]
            ],
            clip_loaders=[
                f"{k}:{v['class_type']}(type={v['inputs'].get('type', '?')})" for k, v in workflow.items()
                if "CLIPLoader" in v["class_type"] or "DualCLIPLoader" in v["class_type"]
            ],
        )
    except Exception:
        logger.debug("diagnostic dlog failed", exc_info=True)
    reset_progress(progress_state)
    progress_state["status"] = "generating"
    if task_id:
        from core.bridge_core import task_registry as _tr
        _tr.update_progress(task_id, 0, 0, 0)
    t0 = time.time()
    t_perf0 = time.perf_counter()
    timing: dict[str, int] = {
        "connect_ws_ms": 0,
        "queue_prompt_ms": 0,
        "wait_for_result_ms": 0,
        "get_images_ms": 0,
        "convert_ms": 0,
        "save_ms": 0,
        "import_submit_ms": 0,
        "image_count": 0,
        "image_bytes": 0,
    }
    pre_ws = client.connect_ws(client_id)
    timing["connect_ws_ms"] = round((time.perf_counter() - t_perf0) * 1000)
    t_q = time.perf_counter()
    try:
        queue_result = client.queue_prompt(workflow, client_id)
        timing["queue_prompt_ms"] = round((time.perf_counter() - t_q) * 1000)
    except BridgeConnectionError as exc:
        progress_state["status"] = "error"
        emit(GEN_ERROR, {"bridge": BRIDGE_TAG, "error": str(exc)}, source=EXT_NAME)
        if pre_ws is not None:
            with contextlib.suppress(Exception):
                pre_ws.close()
        return api_error("ComfyUI connection failed", 502)
    except BridgeHTTPError as exc:
        progress_state["status"] = "error"
        emit(GEN_ERROR, {"bridge": BRIDGE_TAG, "error": f"HTTP {exc.status}"}, source=EXT_NAME)
        if pre_ws is not None:
            with contextlib.suppress(Exception):
                pre_ws.close()
        return api_error(f"ComfyUI error: HTTP {exc.status}", 502)

    prompt_id = queue_result.get("prompt_id", "")
    if not prompt_id:
        progress_state["status"] = "error"
        if pre_ws is not None:
            with contextlib.suppress(Exception):
                pre_ws.close()
        return api_error("No prompt_id returned from ComfyUI", 502)

    last_progress_step = 0
    last_progress_total = 0

    def _on_progress(value: int, max_val: int) -> None:
        nonlocal last_progress_step, last_progress_total
        last_progress_step = value
        last_progress_total = max_val
        if task_id:
            # Per-task registry is authoritative when task_id is set; skip the
            # shared progress_state to avoid concurrent-request stomping.
            from core.bridge_core import task_registry as _tr
            pct = int(value / max_val * 100) if max_val > 0 else 0
            _tr.update_progress(task_id, pct, value, max_val)
        else:
            progress_state["step"] = value
            progress_state["total_steps"] = max_val
            if max_val > 0:
                progress_state["progress"] = value / max_val
        progress_pct = (value / max_val) if max_val > 0 else 0.0
        emit(
            GEN_PROGRESS,
            {"bridge": BRIDGE_TAG, "progress": progress_pct, "step": value, "total_steps": max_val},
            source=EXT_NAME,
        )

    t_wait = time.perf_counter()
    try:
        client.wait_for_result(prompt_id, client_id, on_progress=_on_progress, timeout=300, pre_ws=pre_ws)
        timing["wait_for_result_ms"] = round((time.perf_counter() - t_wait) * 1000)
    except RuntimeError as exc:
        err_str = str(exc)
        progress_state["status"] = "error"
        emit(GEN_ERROR, {"bridge": BRIDGE_TAG, "error": err_str}, source=EXT_NAME)
        logger.warning("ComfyUI workflow execution failed: %s", exc)
        if "meta tensor" in err_str.lower():
            return api_error(
                "CLIP またはモデルの指定が間違っている可能性があります。"
                " comfyui_list_text_encoders で利用可能なテキストエンコーダを確認し、"
                " text_encoder_1 / clip_type の組み合わせを見直してください。"
                f" (詳細: {err_str})",
                502,
            )
        return api_error(f"ComfyUI execution failed: {err_str}", 502)
    finally:
        if pre_ws is not None:
            with contextlib.suppress(Exception):
                pre_ws.close()

    t_imgs = time.perf_counter()
    images = client.get_images(prompt_id)
    timing["get_images_ms"] = round((time.perf_counter() - t_imgs) * 1000)
    timing["image_count"] = len(images)
    timing["image_bytes"] = sum(len(img.get("base64") or "") for img in images)

    # Log ComfyUI history status for diagnosing mosaic / silent execution errors.
    try:
        from core.infra_core.debug_log import dlog as _dlog
        try:
            from .comfyui_client_wait import get_history as _get_history
        except ImportError:  # pragma: no cover - direct import path
            from comfyui_client_wait import get_history as _get_history
        _hist = _get_history(client._http, prompt_id)
        _status = _hist.get("status", {})
        _outputs = _hist.get("outputs", {})
        _output_keys = {nid: list(out.keys()) for nid, out in _outputs.items()}
        _dlog(
            "comfyui_bridge",
            "execute_workflow.history",
            prompt_id=prompt_id,
            status_str=_status.get("status_str", "?"),
            completed=_status.get("completed"),
            image_count=len(images),
            output_nodes=_output_keys,
            messages=_status.get("messages", []),
        )
    except Exception:
        logger.debug("diagnostic dlog failed", exc_info=True)
    elapsed_ms = int((time.time() - t0) * 1000)
    if task_id:
        from core.bridge_core import task_registry as _tr
        _tr.update_progress(task_id, 100, last_progress_step, last_progress_total)
    else:
        progress_state["status"] = "done"
        progress_state["progress"] = 1
    t_conv = time.perf_counter()
    if image_format != "png" and images:
        images = convert_images(images, image_format)
    timing["convert_ms"] = round((time.perf_counter() - t_conv) * 1000)

    saved_paths: list[str] = []
    saved_items: list[dict] | None = None
    save_folder = get_extension_config_value(EXT_NAME, "save_folder", "")
    auto_save = get_extension_config_value(EXT_NAME, "auto_save", False)
    bridge_managed = bool(get_extension_config_value(EXT_NAME, "bridge_managed_save", False))
    bridge_managed_fallback = False

    comfy_output_root = ""
    if bridge_managed and images:
        comfy_output_root = resolve_sweep_xmp_target()
        if not comfy_output_root:
            logger.warning(
                "bridge_managed_save is on but comfy_output_root is not set; "
                "skipping XMP write to ComfyUI outputs",
            )
        elif sweep_meta:
            from core.bridge_core.sweep_xmp import write_sweep_xmp_to_paths
            try:
                descs = client.get_output_paths(prompt_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to fetch ComfyUI output paths: %s", exc)
                descs = []
            abs_paths: list[str] = []
            root = Path(comfy_output_root).expanduser()
            for d in descs:
                if d.get("type") != "output":
                    continue
                fname = d.get("filename") or ""
                if not fname:
                    continue
                sub = d.get("subfolder") or ""
                p = resolve_comfy_output_path(root, sub, fname)
                if p is not None:
                    abs_paths.append(str(p))
                else:
                    logger.warning(
                        "Rejected unsafe or missing ComfyUI output path: subfolder=%r filename=%r",
                        sub,
                        fname,
                    )
            if abs_paths:
                from core.bridge_core.sweep_db import upsert_sweep_from_meta
                with contextlib.suppress(Exception):
                    write_sweep_xmp_to_paths(abs_paths, sweep_meta)
                if get_extension_config_value(EXT_NAME, "auto_import", True):
                    if sweep_meta:
                        mapping = import_saved_files_sync(abs_paths)
                        saved_items = [
                            {"path": p, "file_id": mapping.get(p)}
                            for p in abs_paths
                        ]
                        for p in abs_paths:
                            upsert_sweep_from_meta(sweep_meta, mapping.get(p))
                    else:
                        import_saved_files_async(abs_paths)
                elif sweep_meta:
                    upsert_sweep_from_meta(sweep_meta, None)
            saved_paths = abs_paths
        bridge_managed_fallback = not saved_paths and bool(comfy_output_root)
        if bridge_managed_fallback:
            logger.warning(
                "bridge_managed_save: no ComfyUI outputs found under %r "
                "(ComfyUI likely wrote elsewhere, e.g. its temp/output dir). "
                "Falling back to save_folder copy. To use bridge_managed_save "
                "without the fallback, set ComfyUI --output-directory to %r.",
                comfy_output_root,
                comfy_output_root,
            )

    if not saved_paths and save_folder and auto_save and images:
        t_save = time.perf_counter()
        raw_bytes = []
        for img in images:
            with contextlib.suppress(Exception):
                raw_bytes.append(b64mod.b64decode(img["base64"]))
        if raw_bytes:
            saved_paths = bridge_save_images(
                raw_bytes,
                -1,
                save_folder,
                image_format=image_format,
                naming=get_extension_config_value(EXT_NAME, "save_naming", "daily_folder"),
                extra_fields=extra_fields,   # pass through for _gen_params embedding
            )
            timing["save_ms"] = round((time.perf_counter() - t_save) * 1000)
            if saved_paths and sweep_meta:
                from core.bridge_core.sweep_xmp import write_sweep_xmp_to_paths
                with contextlib.suppress(Exception):
                    write_sweep_xmp_to_paths(saved_paths, sweep_meta)
            if saved_paths and get_extension_config_value(EXT_NAME, "auto_import", True):
                t_imp = time.perf_counter()
                if sweep_meta:
                    from core.bridge_core.sweep_db import upsert_sweep_from_meta
                    mapping = import_saved_files_sync(saved_paths)
                    saved_items = [
                        {"path": p, "file_id": mapping.get(p)}
                        for p in saved_paths
                    ]
                    for p in saved_paths:
                        upsert_sweep_from_meta(sweep_meta, mapping.get(p))
                else:
                    import_saved_files_async(saved_paths)
                timing["import_submit_ms"] = round((time.perf_counter() - t_imp) * 1000)
            elif saved_paths and sweep_meta:
                from core.bridge_core.sweep_db import upsert_sweep_from_meta
                upsert_sweep_from_meta(sweep_meta, None)

    if elapsed_ms >= 1000:
        try:
            from core.infra_core.debug_log import dlog
            dlog(
                "comfyui_bridge",
                "generate.slow",
                total_ms=elapsed_ms,
                **timing,
            )
        except Exception:
            logger.debug("diagnostic dlog failed", exc_info=True)
    emit(GEN_COMPLETE, {"bridge": BRIDGE_TAG, "images_count": len(images), "elapsed_ms": elapsed_ms}, source=EXT_NAME)
    resp: dict = {"images": images, "prompt_id": prompt_id, "elapsed_ms": elapsed_ms, "image_format": image_format}
    if extra_fields:
        resp.update(extra_fields)
    if saved_paths:
        resp["saved"] = saved_paths
    if saved_items is not None:
        resp["saved_items"] = saved_items
    if bridge_managed:
        resp["bridge_managed_save"] = True
    if bridge_managed_fallback:
        resp["bridge_managed_save_fallback"] = True
    return api_success(resp)
