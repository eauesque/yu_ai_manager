"""Generation logic facade for the ComfyUI Bridge extension."""

from __future__ import annotations

import base64
import binascii
import logging
import re
from typing import Any
from urllib.parse import urlsplit

from core.bridge_core import BridgeConnectionError

logger = logging.getLogger(__name__)

# Hard cap on img2img source size (front-end pre-flight is 3 MB; this is the
# server-side safety net that also covers external API callers).
MAX_IMG2IMG_BYTES = 50 * 1024 * 1024

# <lora:NAME:STRENGTH_MODEL[:STRENGTH_CLIP]>
# NAME may contain path separators, dots, hyphens; strengths are floats.
_LORA_TOKEN_RE = re.compile(
    r"<lora:([^:>]+?)(?::(-?\d+(?:\.\d+)?))?(?::(-?\d+(?:\.\d+)?))?>"
)


def _extract_lora_tokens(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Strip `<lora:name:weight>` tokens from prompt and return (cleaned, loras)."""
    loras: list[dict[str, Any]] = []

    def _take(match: re.Match[str]) -> str:
        name = match.group(1).strip()
        sm = float(match.group(2)) if match.group(2) else 1.0
        sc = float(match.group(3)) if match.group(3) else sm
        loras.append({"name": name, "strength_model": sm, "strength_clip": sc})
        return ""

    cleaned = _LORA_TOKEN_RE.sub(_take, text)
    # Collapse empty slots left by removed tokens: ", , " -> ", ", trim whitespace runs.
    cleaned = re.sub(r"(,\s*){2,}", ", ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,")
    return cleaned, loras


def _extract_seed_from_workflow(workflow: dict) -> int:
    """Extract the actual seed used from a built workflow dict.

    Looks for KSampler.inputs.seed or RandomNoise.inputs.noise_seed.
    Returns -1 if not found.
    """
    for node in workflow.values():
        ct = node.get("class_type", "")
        inputs = node.get("inputs", {})
        if ct == "KSampler" and "seed" in inputs:
            try:
                return int(inputs["seed"])
            except (ValueError, TypeError):
                pass
        if ct == "RandomNoise" and "noise_seed" in inputs:
            try:
                return int(inputs["noise_seed"])
            except (ValueError, TypeError):
                pass
    return -1


def _infer_unet_components(diffusion_model: str, client: Any) -> dict[str, str]:
    """Infer VAE and text-encoder for a UNETLoader model using the model registry.

    Returns a dict with zero or more of: ``vae_name``, ``text_encoder_1``,
    ``clip_type``.  Values are empty string when nothing could be matched.

    Lookup order: user registry entries → built-in registry entries → first available.
    The registry can be extended at runtime via the model registry API / MCP tools
    without source code changes.

    Notes:
      - wan clip_type: umT5-XXL has vocab size 256,384 (vs standard T5's 32,128).
        CLIPLoader type="wan" selects the correct tokenizer; leaving empty causes
        vocab size mismatch on load.
      - anima clip_type: uses qwen_3_06b (standard Qwen3-0.6B CLIP), verified
        against anima_baseV10 WebUI workflow.
    """
    try:
        from .comfyui_model_registry import find_entry_for_model
    except ImportError:  # pragma: no cover - top-level extension import path
        from comfyui_model_registry import find_entry_for_model  # type: ignore[no-redef]

    entry = find_entry_for_model(diffusion_model)
    if entry is not None:
        vae_hint: str | None = entry.vae or None
        clip_hint: str | None = entry.clip_1 or None
        clip_type_hint: str = entry.clip_type
    else:
        vae_hint, clip_hint, clip_type_hint = None, None, ""

    try:
        available_vaes: list[str] = client.list_models_by_loader("VAELoader", "vae_name")
    except Exception:
        available_vaes = []
    try:
        available_clips: list[str] = client.list_text_encoders()
    except Exception:
        available_clips = []

    result: dict[str, str] = {}

    if vae_hint:
        vae_hint_lower = vae_hint.lower()
        matched = [v for v in available_vaes if vae_hint_lower in v.lower()]
        result["vae_name"] = matched[0] if matched else (available_vaes[0] if available_vaes else "")
    else:
        result["vae_name"] = available_vaes[0] if available_vaes else ""

    if clip_hint:
        clip_hint_lower = clip_hint.lower()
        matched = [c for c in available_clips if clip_hint_lower in c.lower()]
        result["text_encoder_1"] = matched[0] if matched else (available_clips[0] if available_clips else "")
    else:
        result["text_encoder_1"] = available_clips[0] if available_clips else ""

    if clip_type_hint:
        result["clip_type"] = clip_type_hint

    return result


def _build_gen_params(params: dict, te_kind: Any, actual_seed: int, denoise: float) -> dict:
    """Build the _gen_params backup dict for embedding in saved images."""
    return {
        "schema_version": 1,
        "loader_type": "unet" if params.get("diffusion_model") else "checkpoint",
        "ckpt_name": params.get("ckpt_name", ""),
        "diffusion_model": params.get("diffusion_model", ""),
        "vae_name": params.get("vae_name", ""),
        "text_encoder_1": params.get("text_encoder_1", ""),
        "text_encoder_2": params.get("text_encoder_2", ""),
        "clip_type": params.get("clip_type", ""),
        "weight_dtype": params.get("weight_dtype", "default"),
        "steps": params.get("steps", 20),
        "cfg": float(params.get("cfg", 8.0)),
        "sampler_name": params.get("sampler_name", "euler"),
        "scheduler": params.get("scheduler", "normal"),
        "seed": actual_seed,
        "width": params.get("width", 512),
        "height": params.get("height", 768),
        "denoise": denoise,
        "loras": params.get("loras", []),
        "text_encoder_kind": str(te_kind) if te_kind is not None else "",
        "a1111_mode": bool(params.get("a1111_mode", False)),
    }

from core.extensions_core.extensions_admin import get_extension_config_value

from core.bridge_core.prompt_expand import maybe_expand_prompt
from core.event_bus import emit
from core.event_bus.event_types import GEN_SUBMIT
from core.infra_core.api_errors import api_error

try:
    from .comfyui_checkpoint_inspect import auto_detect_models_root
    from .comfyui_client import ComfyUIClient
    from .comfyui_client_upload import upload_image
    from .comfyui_generate_convert import convert_images
    from .comfyui_generate_execute import execute_workflow as _execute_workflow
    from .comfyui_generate_execute import reset_progress
    from .comfyui_text_encoder import TEXT_ENCODER_NODE_MAP, TextEncoderKind, detect_text_encoder_kind, te1_kind_hint
    from .comfyui_workflows import build_txt2img_workflow
    from .comfyui_workflows_img2img import build_img2img_workflow
except ImportError:  # pragma: no cover - top-level extension import path
    from comfyui_checkpoint_inspect import auto_detect_models_root
    from comfyui_client import ComfyUIClient
    from comfyui_client_upload import upload_image
    from comfyui_generate_convert import convert_images
    from comfyui_generate_execute import execute_workflow as _execute_workflow
    from comfyui_generate_execute import reset_progress
    from comfyui_text_encoder import TEXT_ENCODER_NODE_MAP, TextEncoderKind, detect_text_encoder_kind, te1_kind_hint
    from comfyui_workflows import build_txt2img_workflow
    from comfyui_workflows_img2img import build_img2img_workflow

EXT_NAME = "builtin-comfyui-bridge"
BRIDGE_TAG = "comfyui"
progress_state: dict[str, Any] = {"progress": 0, "step": 0, "total_steps": 0, "status": "idle"}

MAX_JSON_WORKFLOW_NODES = 200
MAX_JSON_WORKFLOW_STRING_LENGTH = 20_000
_JSON_WORKFLOW_DANGEROUS_CLASS_RE = re.compile(
    r"(?:url|uri|http|request|download|webhook|socket|exec|command|shell|subprocess|python|script)",
    re.IGNORECASE,
)
_JSON_WORKFLOW_SECRET_KEY_RE = re.compile(
    r"(?:api[_-]?key|token|secret|password|passwd|authorization|cookie)",
    re.IGNORECASE,
)
_JSON_WORKFLOW_EXTERNAL_REF_RE = re.compile(
    r"(?i)\b(?P<scheme>https?|ftp|file)://[^\s\"'<>]+"
)
_JSON_WORKFLOW_ABSOLUTE_PATH_RE = re.compile(r"^(?:/|~[/\\]|[a-zA-Z]:[/\\]|\\\\)")
_JSON_WORKFLOW_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _json_workflow_has_external_ref(value: str) -> bool:
    for match in _JSON_WORKFLOW_EXTERNAL_REF_RE.finditer(value):
        scheme = match.group("scheme").lower()
        if scheme not in {"http", "https"}:
            return True
        try:
            host = urlsplit(match.group(0)).hostname
        except ValueError:
            return True
        if (host or "").lower().rstrip(".") not in _JSON_WORKFLOW_LOOPBACK_HOSTS:
            return True
    return False


def _validate_json_workflow(workflow: dict[str, Any]) -> str | None:
    if len(workflow) > MAX_JSON_WORKFLOW_NODES:
        return f"workflow has too many nodes (max {MAX_JSON_WORKFLOW_NODES})"
    for node_id, node in workflow.items():
        if not isinstance(node_id, str) or len(node_id) > 128:
            return "workflow node id is invalid"
        if not isinstance(node, dict):
            return f"workflow node {node_id} must be an object"
        class_type = node.get("class_type")
        if not isinstance(class_type, str) or not class_type.strip():
            return f"workflow node {node_id} class_type is required"
        if _JSON_WORKFLOW_DANGEROUS_CLASS_RE.search(class_type):
            return f"workflow node {node_id} class_type is not allowed"
        inputs = node.get("inputs", {})
        if inputs is None:
            inputs = {}
        if not isinstance(inputs, dict):
            return f"workflow node {node_id} inputs must be an object"
        err = _validate_json_workflow_value(inputs, path=f"node {node_id}.inputs")
        if err:
            return err
    return None


def _validate_json_workflow_value(value: Any, *, path: str) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_s = str(key)
            child_path = f"{path}.{key_s}"
            if _JSON_WORKFLOW_SECRET_KEY_RE.search(key_s):
                return f"workflow input {child_path} is not allowed"
            err = _validate_json_workflow_value(child, path=child_path)
            if err:
                return err
        return None
    if isinstance(value, list):
        if len(value) > 1000:
            return f"workflow input {path} has too many values"
        for idx, child in enumerate(value):
            err = _validate_json_workflow_value(child, path=f"{path}[{idx}]")
            if err:
                return err
        return None
    if isinstance(value, str):
        if len(value) > MAX_JSON_WORKFLOW_STRING_LENGTH:
            return f"workflow input {path} is too long"
        if "\x00" in value or _json_workflow_has_external_ref(value):
            return f"workflow input {path} contains an external reference"
        if (
            _JSON_WORKFLOW_ABSOLUTE_PATH_RE.search(value)
            or "../" in value
            or "..\\" in value
        ):
            return f"workflow input {path} contains an unsafe path"
        return None
    if isinstance(value, (int, float, bool)) or value is None:
        return None
    return f"workflow input {path} has unsupported type"


def _validate_sweep_xmp_target(data: dict[str, Any]):
    """Refuse to generate if Sweep is enabled but the XMP embed target is unset.

    Without a target path (= ComfyUI's local output directory), the bridge
    silently drops Sweep XMP write and the user is left with un-tagged copies
    inside ComfyUI's output dir while the bridge logs nothing visible.
    """
    if not data.get("sweep_meta"):
        return None
    if not bool(get_extension_config_value(EXT_NAME, "bridge_managed_save", False)):
        return None
    try:
        from .comfyui_generate_execute import resolve_sweep_xmp_target
    except ImportError:  # pragma: no cover
        from comfyui_generate_execute import resolve_sweep_xmp_target
    if (resolve_sweep_xmp_target() or "").strip():
        return None
    return api_error(
        "Sweep XMP 埋め込みが ON ですが、埋め込み先パス (ComfyUI 側 output ディレクトリ) "
        "が未設定です。設定タブで指定してください。",
        400,
    )


def generate_simple(
    data: dict[str, Any],
    client: ComfyUIClient,
    client_id: str,
    *,
    task_id: str | None = None,
):
    err = _validate_sweep_xmp_target(data)
    if err:
        return err
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return api_error("prompt is required", 400)

    negative = (data.get("negative_prompt") or "").strip()

    def _clamp_int(val: Any, default: int, lo: int, hi: int) -> int:
        try:
            return max(lo, min(int(val), hi))
        except (ValueError, TypeError):
            return default

    # batch_size: clamp to server-side max_batch_size to prevent VRAM overload.
    _max_batch_size = get_extension_config_value(EXT_NAME, "max_batch_size", 8)
    _batch_size = _clamp_int(data.get("batch_size", 1), 1, 1, _max_batch_size)

    params = {
        "ckpt_name": data.get("ckpt_name", ""),
        "vae_name": data.get("vae_name", ""),
        "steps": _clamp_int(data.get("steps", 20), 20, 1, 200),
        "sampler_name": data.get("sampler_name", "euler"),
        "scheduler": data.get("scheduler", "normal"),
        "cfg": max(0.0, min(float(data.get("cfg", 8.0)), 30.0)),
        "width": _clamp_int(data.get("width", 512), 512, 64, 16384),
        "height": _clamp_int(data.get("height", 768), 768, 64, 16384),
        "seed": _clamp_int(data.get("seed", -1), -1, -1, 2**32 - 1),
        "batch_size": _batch_size,
        "diffusion_model": data.get("diffusion_model", ""),
        "text_encoder_1": data.get("text_encoder_1", ""),
        "text_encoder_2": data.get("text_encoder_2", ""),
        "clip_type": data.get("clip_type", ""),
        "weight_dtype": data.get("weight_dtype", "default"),
        "controlnet_model": data.get("controlnet_model", ""),
        "controlnet_strength": float(data.get("controlnet_strength", 1.0)),
        "controlnet_image_name": data.get("controlnet_image_name", ""),
        "upscale_model": data.get("upscale_model", ""),
        "a1111_mode": bool(data.get("a1111_mode", False)),
    }

    # LoRA: accept both structured `loras` param and `<lora:NAME:WEIGHT>` prompt tokens.
    lora_list: list[dict[str, Any]] = []
    raw_loras = data.get("loras")
    if isinstance(raw_loras, list):
        for entry in raw_loras:
            if isinstance(entry, dict) and entry.get("name"):
                lora_list.append(
                    {
                        "name": str(entry["name"]),
                        "strength_model": float(entry.get("strength_model", 1.0)),
                        "strength_clip": float(entry.get("strength_clip", entry.get("strength_model", 1.0))),
                    }
                )
    prompt, extracted = _extract_lora_tokens(prompt)
    lora_list.extend(extracted)
    if lora_list:
        params["loras"] = lora_list

    # ── Text encoder kind detection ──────────────────────────────────────────
    # separate-load mode: infer from text_encoder_1 filename to guard BNK safety.
    #   Qwen3-based encoders (Anima, Qwen-Image) → QWEN3, supports_a1111_adv=False.
    #   CLIP-based encoders → None, a1111_mode alone decides (legacy behaviour).
    # checkpoint mode: auto-detect from safetensors header + filename heuristics.
    if params["diffusion_model"]:
        # Auto-fill vae_name / text_encoder_1 if the caller did not provide them.
        # Use filename heuristics (wan/qwen/anima families) with list-based fallback.
        if not params["vae_name"] or not params["text_encoder_1"]:
            _inferred = _infer_unet_components(params["diffusion_model"], client)
            _auto_filled: list[str] = []
            if not params["vae_name"] and _inferred.get("vae_name"):
                params["vae_name"] = _inferred["vae_name"]
                _auto_filled.append(f"vae_name={_inferred['vae_name']!r}")
            if not params["text_encoder_1"] and _inferred.get("text_encoder_1"):
                params["text_encoder_1"] = _inferred["text_encoder_1"]
                _auto_filled.append(f"text_encoder_1={_inferred['text_encoder_1']!r}")
            if not params["clip_type"] and _inferred.get("clip_type"):
                params["clip_type"] = _inferred["clip_type"]
                _auto_filled.append(f"clip_type={_inferred['clip_type']!r}")
            if _auto_filled:
                logger.info(
                    "comfyui auto-inferred for diffusion_model=%s: %s",
                    params["diffusion_model"], ", ".join(_auto_filled),
                )

        te1 = params.get("text_encoder_1") or ""
        te_kind = te1_kind_hint(te1)   # QWEN3 for qwen/anima encoders, else None
        te_source = "separate_load_filename" if te_kind is not None else "separate_load"
        logger.info(
            "text_encoder_kind=%s (%s) diffusion_model=%s te1=%s",
            te_kind, te_source, params["diffusion_model"], te1,
        )
    else:
        if not params["ckpt_name"]:
            # Give LLM callers actionable guidance on which mode to use.
            try:
                _ckpts = client.list_models()
                _unets = client.list_diffusion_models()
            except Exception:
                _ckpts = []
                _unets = []
            if not _ckpts and _unets:
                _unet_preview = ", ".join(_unets[:3]) + ("..." if len(_unets) > 3 else "")
                return api_error(
                    f"checkpoints が空のため ckpt_name を指定できません。"
                    f" diffusion_model に UNETLoader モデルを指定してください"
                    f" (利用可能: {_unet_preview})。"
                    f" text_encoder_1 と vae_name も必須です"
                    f" (comfyui_list_text_encoders / comfyui_discovery_models で確認)。",
                    400,
                )
            if _ckpts:
                _ckpt_preview = ", ".join(_ckpts[:3]) + ("..." if len(_ckpts) > 3 else "")
                return api_error(
                    f"ckpt_name が必須です。利用可能: {_ckpt_preview}",
                    400,
                )
            return api_error(
                "ckpt_name または diffusion_model が必須です。"
                " comfyui_list_models / comfyui_list_diffusion_models で利用可能なモデルを確認してください。",
                400,
            )
        models_root = get_extension_config_value(EXT_NAME, "models_root", "")
        if not models_root:
            models_root = auto_detect_models_root(
                get_extension_config_value(EXT_NAME, "api_url", "http://127.0.0.1:8188")
            )
        te_kind, te_source = detect_text_encoder_kind(params["ckpt_name"], models_root)
        logger.info(
            "text_encoder_kind=%s source=%s ckpt=%s",
            te_kind, te_source, params["ckpt_name"],
        )

    # Add te_kind to params for emit payload (str Enum serialises as plain string)
    if te_kind is not None:
        params["text_encoder_kind"] = te_kind

    if params["diffusion_model"] and not params["vae_name"]:
        return api_error(
            "vae_name が未指定かつ自動検出できませんでした。"
            " comfyui_discovery_models で利用可能な VAE を確認し、vae_name を指定してください。",
            400,
        )
    if params["diffusion_model"] and not params["text_encoder_1"]:
        return api_error(
            "text_encoder_1 が未指定かつ自動検出できませんでした。"
            " comfyui_list_text_encoders で利用可能なテキストエンコーダを確認し、text_encoder_1 を指定してください。",
            400,
        )

    # BNK node availability check — only required when BNK is actually intended.
    # te_kind=None (separate-load / legacy): a1111_mode alone decides
    # te_kind set: only check if supports_a1111_adv=True for this architecture
    _unknown_recipe = TEXT_ENCODER_NODE_MAP[TextEncoderKind.UNKNOWN]
    adv_intended = params["a1111_mode"] and (
        te_kind is None or TEXT_ENCODER_NODE_MAP.get(te_kind, _unknown_recipe).supports_a1111_adv
    )
    if adv_intended and not client.has_node("BNK_CLIPTextEncodeAdvanced"):
        return api_error(
            "AUTOMATIC1111 互換モードには ComfyUI カスタムノード "
            "'ComfyUI_ADV_CLIP_emb' が必要です。インストールするか、互換モードを OFF にしてください。",
            400,
        )

    # UNKNOWN kind + a1111_mode=True: log a warning and disable BNK for safety
    encoder_warning: str | None = None
    if te_kind == TextEncoderKind.UNKNOWN and params["a1111_mode"]:
        encoder_warning = (
            "encoder type unknown; A1111 mode disabled for safety (using CLIPTextEncode)"
        )
        logger.warning(
            "text encoder unknown, a1111_mode forced off for ckpt=%s", params["ckpt_name"]
        )

    expansion = maybe_expand_prompt(
        prompt,
        negative,
        bool(data.get("expand_wildcards", False)),
        seed=params["seed"] if params["seed"] not in (-1, None) else None,
        extra_wildcards=data.get("client_wildcards") if isinstance(data.get("client_wildcards"), dict) else None,
    )
    prompt = expansion["prompt"]
    negative = expansion["negative"]
    if expansion["expanded"]:
        from importlib import import_module

        engine = import_module("extensions.builtin_sd_nai_convert.core_impl.sd_nai_convert_engine")
        prompt = engine.convert_nai_to_sd(prompt)
        negative = engine.convert_nai_to_sd(negative)
        expansion["prompt"] = prompt

    image_format = (data.get("image_format") or "png").strip().lower()
    if image_format not in ("png", "webp", "jpg"):
        image_format = "png"

    save_folder = get_extension_config_value(EXT_NAME, "save_folder", "")
    auto_save = get_extension_config_value(EXT_NAME, "auto_save", False)
    # skip_save: per-request flag from client (e.g. Sweep deferred-save mode)
    # to bypass auto-save and use a temp PreviewImage workflow node instead.
    skip_save = bool(data.get("skip_save"))
    use_preview = bool(save_folder and auto_save) and not skip_save

    image_b64 = data.get("image_base64")
    mode = "simple"
    gen_params: dict[str, Any] = {}
    if image_b64:
        # img2img: decode, upload to ComfyUI, build img2img workflow
        try:
            img_bytes = base64.b64decode(image_b64, validate=True)
        except (binascii.Error, ValueError):
            return api_error("image_base64 invalid", 400)
        if len(img_bytes) > MAX_IMG2IMG_BYTES:
            return api_error(
                f"image too large (max {MAX_IMG2IMG_BYTES // (1024 * 1024)} MB)", 400,
            )
        try:
            uploaded_name = upload_image(client.api_url, img_bytes, "from_bridge.png")
        except BridgeConnectionError as exc:
            logger.warning("img2img upload_image failed: %s", exc)
            return api_error(f"upload to ComfyUI failed: {exc}", 503)

        denoise = float(data.get("denoise", 0.75))
        i2i_params = {
            k: v for k, v in params.items()
            if k not in ("controlnet_model", "controlnet_strength",
                         "controlnet_image_name", "upscale_model", "width", "height",
                         "text_encoder_kind")
        }
        workflow = build_img2img_workflow(
            prompt,
            negative,
            init_image_name=uploaded_name,
            denoise=denoise,
            use_preview=use_preview,
            text_encoder_kind=te_kind,
            **i2i_params,
        )
        actual_seed = _extract_seed_from_workflow(workflow)
        gen_params = _build_gen_params(params, te_kind, actual_seed, float(data.get("denoise", 0.75)))
        mode = "img2img"
    else:
        wf_params = {k: v for k, v in params.items() if k != "text_encoder_kind"}
        workflow = build_txt2img_workflow(
            prompt,
            negative,
            use_preview=use_preview,
            text_encoder_kind=te_kind,
            **wf_params,
        )
        actual_seed = _extract_seed_from_workflow(workflow)
        gen_params = _build_gen_params(params, te_kind, actual_seed, 1.0)

    emit(GEN_SUBMIT, {"bridge": BRIDGE_TAG, "mode": mode, "prompt_preview": prompt[:120], "params": params}, source=EXT_NAME)
    extra = {"expanded_prompt": prompt, "final_negative": negative}
    if expansion["expanded"]:
        extra["original_prompt"] = expansion["original_prompt"]
    if encoder_warning:
        extra["encoder_fallback_warning"] = encoder_warning
    extra["_gen_params"] = gen_params
    return execute_workflow(
        workflow, client, client_id,
        image_format=image_format, extra_fields=extra,
        sweep_meta=data.get("sweep_meta"),
        task_id=task_id,
    )


def generate_json(
    data: dict[str, Any],
    client: ComfyUIClient,
    client_id: str,
    *,
    task_id: str | None = None,
):
    err = _validate_sweep_xmp_target(data)
    if err:
        return err
    workflow = data.get("workflow")
    if not isinstance(workflow, dict) or not workflow:
        return api_error("workflow (JSON object) is required for json mode", 400)
    err_msg = _validate_json_workflow(workflow)
    if err_msg:
        return api_error(err_msg, 400)
    emit(GEN_SUBMIT, {"bridge": BRIDGE_TAG, "mode": "json", "node_count": len(workflow)}, source=EXT_NAME)
    return execute_workflow(workflow, client, client_id, sweep_meta=data.get("sweep_meta"), task_id=task_id)


def execute_workflow(
    workflow: dict, client: ComfyUIClient, client_id: str,
    image_format: str = "png",
    extra_fields: dict[str, Any] | None = None,
    sweep_meta: dict[str, Any] | None = None,
    task_id: str | None = None,
):
    return _execute_workflow(
        workflow, client, client_id, progress_state,
        image_format=image_format, extra_fields=extra_fields,
        sweep_meta=sweep_meta,
        task_id=task_id,
    )


__all__ = [
    "convert_images",
    "execute_workflow",
    "generate_json",
    "generate_simple",
    "progress_state",
    "reset_progress",
]
