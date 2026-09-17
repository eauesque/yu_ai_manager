"""Extract ComfyUI workflow JSON from image metadata.

Supports PNG (iTXt/tEXt chunks) and WebP/JPEG (EXIF UserComment).

Priority order:
  1. iTXt/tEXt "prompt" key  -> format="api"
  2. iTXt/tEXt "workflow" key -> format="editor"
"""

from __future__ import annotations

import io
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Model-node inspection helpers
# ---------------------------------------------------------------------------

# class_type -> list of (inputs_key, gen_params_key) mappings
_MODEL_NODE_MAP: dict[str, list[tuple[str, str]]] = {
    "CheckpointLoaderSimple": [("ckpt_name", "ckpt_name")],
    "UNETLoader":             [("unet_name", "diffusion_model")],
    "DualCLIPLoader":         [("clip_name1", "text_encoder_1"),
                               ("clip_name2", "text_encoder_2")],
    "CLIPLoader":             [("clip_name", "text_encoder_1")],
    "VAELoader":              [("vae_name", "vae_name")],
}

_LOADER_TYPE_MAP: dict[str, str] = {
    "CheckpointLoaderSimple": "checkpoint",
    "UNETLoader":             "unet",
    "DualCLIPLoader":         "unet",
    "CLIPLoader":             "unet",
    "VAELoader":              "checkpoint",
}

# (class_type → {inputs_key → gen_params_key}) for supplement operations
_SUPPLEMENT_MAP: dict[str, dict[str, str]] = {
    "CheckpointLoaderSimple": {"ckpt_name": "ckpt_name"},
    "UNETLoader":             {"unet_name": "diffusion_model"},
    "DualCLIPLoader":         {"clip_name1": "text_encoder_1",
                               "clip_name2": "text_encoder_2",
                               "type":       "clip_type"},
    "CLIPLoader":             {"clip_name": "text_encoder_1",
                               "type":      "clip_type"},
    "VAELoader":              {"vae_name": "vae_name"},
}


def _is_empty(value: Any) -> bool:
    """Return True if a workflow inputs value is considered missing."""
    if value is None:
        return True
    s = str(value).strip()
    return s in ("", "undefined", "null", "None")


def check_model_nodes(
    workflow: dict[str, Any],
    gen_params: dict[str, Any] | None,
) -> dict[str, Any]:
    """Inspect workflow model nodes and determine queue readiness.

    Returns a dict with keys:
        status: "ok" | "supplement_available" | "warning_no_backup"
        loader_type: "checkpoint" | "unet" | "unknown"  (when status != ok)
        supplement_model_info: dict  (when status == supplement_available)
        message: str  (when status == warning_no_backup)
    """
    # Collect all empty (class_type, inputs_key, gen_params_key) triples
    empty_slots: list[tuple[str, str, str]] = []
    loader_type = "unknown"

    for node in workflow.values():
        ct = node.get("class_type", "")
        mappings = _MODEL_NODE_MAP.get(ct)
        if not mappings:
            continue
        inputs = node.get("inputs", {})
        for inp_key, gp_key in mappings:
            if _is_empty(inputs.get(inp_key)):
                empty_slots.append((ct, inp_key, gp_key))
                loader_type = _LOADER_TYPE_MAP.get(ct, "unknown")

    if not empty_slots:
        return {"status": "ok"}

    # Check if every empty slot has a non-empty backup
    if gen_params:
        all_supplementable = all(
            not _is_empty(gen_params.get(gp_key, ""))
            for _, _, gp_key in empty_slots
        )
        if all_supplementable:
            return {
                "status": "supplement_available",
                "loader_type": loader_type,
                "supplement_model_info": {
                    "ckpt_name":        gen_params.get("ckpt_name", ""),
                    "diffusion_model":  gen_params.get("diffusion_model", ""),
                    "vae_name":         gen_params.get("vae_name", ""),
                    "text_encoder_1":   gen_params.get("text_encoder_1", ""),
                    "text_encoder_2":   gen_params.get("text_encoder_2", ""),
                    "clip_type":        gen_params.get("clip_type", ""),
                },
            }

    return {
        "status": "warning_no_backup",
        "loader_type": loader_type,
        "message": (
            "モデルノードが未設定で、生成時のバックアップ情報もありません。"
            "ComfyUI 側で手動設定が必要です。"
        ),
    }


def supplement_model_nodes(
    workflow: dict[str, Any],
    gen_params: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fill empty model node inputs from gen_params backup.

    Returns (modified_workflow, applied_dict) where applied_dict maps
    the inputs key that was filled to the value used.
    Only fills inputs that are currently empty (does not overwrite).
    """
    import copy
    workflow = copy.deepcopy(workflow)
    applied: dict[str, Any] = {}

    for node in workflow.values():
        ct = node.get("class_type", "")
        key_map = _SUPPLEMENT_MAP.get(ct)
        if not key_map:
            continue
        inputs = node.get("inputs", {})
        for inp_key, gp_key in key_map.items():
            if _is_empty(inputs.get(inp_key)):
                backup_val = gen_params.get(gp_key, "")
                if not _is_empty(backup_val):
                    inputs[inp_key] = backup_val
                    applied[inp_key] = backup_val

    return workflow, applied


def migrate_clip_types(workflow: dict[str, Any]) -> dict[str, Any]:
    """Correct stale clip_type values in CLIPLoader / DualCLIPLoader nodes.

    Old images generated before the qwen_image fix may contain
    type="wan" or type="stable_diffusion" for QWEN3-based text encoders
    (Anima / Qwen-Image series). Re-queuing them would produce mosaic output.

    Re-detect from the encoder filename using te1_kind_hint() and overwrite
    stale values. Only corrects to known-good values; unknown encoders are
    left untouched.
    """
    import copy

    try:
        from .comfyui_text_encoder import TextEncoderKind, te1_kind_hint
    except ImportError:  # pragma: no cover - direct import path
        from comfyui_text_encoder import TextEncoderKind, te1_kind_hint

    # Maps TextEncoderKind → correct ComfyUI CLIPLoader.type
    _KIND_TO_CLIP_TYPE: dict[str, str] = {
        TextEncoderKind.QWEN3: "qwen_image",
    }

    workflow = copy.deepcopy(workflow)
    for node in workflow.values():
        ct = node.get("class_type", "")
        if ct not in ("CLIPLoader", "DualCLIPLoader"):
            continue
        inputs = node.get("inputs", {})
        te1 = inputs.get("clip_name") or inputs.get("clip_name1") or ""
        if not te1:
            continue
        kind = te1_kind_hint(te1)
        correct_type = _KIND_TO_CLIP_TYPE.get(str(kind))
        if correct_type and inputs.get("type") != correct_type:
            logger.info(
                "migrate_clip_types: %s type %r → %r (te1=%r)",
                ct, inputs.get("type"), correct_type, te1,
            )
            inputs["type"] = correct_type
    return workflow


def extract_gen_params_from_image(
    image_bytes: bytes, filename: str,
) -> dict[str, Any] | None:
    """Extract _gen_params backup dict from an image's metadata.

    Returns the parsed _gen_params dict or None if not found/invalid.
    Supports PNG (tEXt/iTXt chunk) and WebP/JPEG (YU_META EXIF envelope).
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    try:
        from PIL import Image
        pil_img = Image.open(io.BytesIO(image_bytes))
    except Exception:
        return None

    # PNG: look for _gen_params tEXt/iTXt chunk
    if ext == "png":
        raw = (pil_img.text or {}).get("_gen_params")
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed
            except (ValueError, TypeError):
                logger.warning("extract_gen_params_from_image: JSON parse failed for PNG _gen_params")
        return None

    # WebP / JPEG: look inside YU_META envelope
    try:
        exif_bytes = pil_img.info.get("exif", b"")
        if not exif_bytes:
            return None
        # Decode EXIF UserComment (YU_META envelope)
        import piexif
        exif_dict = piexif.load(exif_bytes)
        uc = exif_dict.get("Exif", {}).get(piexif.ExifIFD.UserComment, b"")
        if not uc:
            return None
        if uc.startswith(b"UNICODE\x00"):
            comment = uc[8:].decode("utf-16-le", errors="replace")
        else:
            comment = uc.decode("utf-8", errors="replace")
        if not comment.startswith("YU_META:"):
            return None
        chunks = json.loads(comment[8:])
        raw = chunks.get("_gen_params")
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed
            except (ValueError, TypeError):
                logger.warning(
                    "extract_gen_params_from_image: _gen_params JSON parse failed for %s", filename
                )
    except Exception:
        logger.warning("extract_gen_params_from_image: failed to parse EXIF for %s", filename)
    return None


def extract_workflow_from_image(
    image_bytes: bytes, filename: str,
) -> dict[str, Any]:
    """Extract workflow JSON from image metadata.

    Returns
    -------
    dict
        ``{"ok": True, "workflow": {...}, "format": "api"|"editor"}``
        or ``{"ok": False, "error": "..."}``
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "png":
        return _extract_png(image_bytes)
    if ext in ("webp", "jpg", "jpeg"):
        return _extract_exif(image_bytes)

    return {"ok": False, "error": f"Unsupported format: {ext}"}


def _extract_png(data: bytes) -> dict[str, Any]:
    """Parse PNG iTXt/tEXt chunks for prompt/workflow keys."""
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data))
        info = img.info or {}
    except Exception as exc:
        return {"ok": False, "error": f"PNG parse error: {exc}"}

    for key, fmt in [("prompt", "api"), ("workflow", "editor")]:
        raw = info.get(key)
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return {"ok": True, "workflow": parsed, "format": fmt}
            except (json.JSONDecodeError, TypeError):
                continue

    return {"ok": False, "error": "No workflow metadata found in PNG"}


def _extract_exif(data: bytes) -> dict[str, Any]:
    """Extract workflow from EXIF UserComment (WebP/JPEG).

    Handles two storage patterns:
    1. YU_META envelope (yu_ai_manager bridge): UserComment contains
       "YU_META:" + JSON-encoded chunk dict.  The "prompt" key in that
       dict holds the ComfyUI API-format workflow.
    2. Raw JSON directly in UserComment (legacy / third-party tools).
    """
    try:
        import piexif
        from PIL import Image

        img = Image.open(io.BytesIO(data))
        exif_data = img.info.get("exif", b"")
        if not exif_data:
            return {"ok": False, "error": "No EXIF data found"}

        exif_dict = piexif.load(exif_data)
        user_comment = exif_dict.get("Exif", {}).get(
            piexif.ExifIFD.UserComment, b""
        )
        if not user_comment:
            return {"ok": False, "error": "No UserComment in EXIF"}

        text = user_comment
        if isinstance(text, bytes):
            if text.startswith(b"UNICODE\x00"):
                text = text[8:].decode("utf-16-le")
            elif text.startswith(b"ASCII\x00\x00\x00"):
                text = text[8:].decode("ascii")
            else:
                text = text.decode("utf-8", errors="replace")

        # --- Pattern 1: YU_META envelope (bridge-generated WebP/JPEG) ---
        if text.startswith("YU_META:"):
            try:
                chunks = json.loads(text[len("YU_META:"):])
            except (json.JSONDecodeError, ValueError):
                return {"ok": False, "error": "YU_META JSON parse error"}
            if not isinstance(chunks, dict):
                return {"ok": False, "error": "YU_META is not a dict"}
            for key, fmt in [("prompt", "api"), ("workflow", "editor")]:
                raw = chunks.get(key)
                if not raw:
                    continue
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        return {"ok": True, "workflow": parsed, "format": fmt}
                except (json.JSONDecodeError, TypeError):
                    continue
            return {"ok": False, "error": "No workflow key in YU_META chunks"}

        # --- Pattern 2: raw JSON directly in UserComment (legacy) ---
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return {"ok": True, "workflow": parsed, "format": "api"}
        except (json.JSONDecodeError, TypeError):
            pass

        return {"ok": False, "error": "No valid workflow in EXIF"}
    except ImportError:
        return {"ok": False, "error": "piexif not installed"}
    except Exception as exc:
        return {"ok": False, "error": f"EXIF parse error: {exc}"}
