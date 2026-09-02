"""Standard ComfyUI workflow templates for Simple mode.

Builds the canonical 7-node txt2img workflow in ComfyUI API format.
"""

from __future__ import annotations

import random


def add_clip_encode_pair(
    workflow: dict,
    prompt: str,
    negative_prompt: str,
    clip_ref: list,
    *,
    a1111_mode: bool = False,
    text_encoder_kind=None,   # TextEncoderKind | None; None = backward compat
    pos_id: str = "6",
    neg_id: str = "7",
) -> None:
    """Insert positive + negative CLIP text encode nodes into ``workflow``.

    When ``a1111_mode`` is True and the text encoder supports it, swaps to
    BNK_CLIPTextEncodeAdvanced (from ``ComfyUI_ADV_CLIP_emb``) with A1111-
    compatible weight normalization so that ``(word:1.3)`` matches A1111/NAI.

    ``text_encoder_kind`` controls BNK eligibility:
    - None (default)  — backward compat: a1111_mode alone decides (legacy)
    - TextEncoderKind — BNK only if kind's recipe has supports_a1111_adv=True
    """
    try:
        from .comfyui_text_encoder import TEXT_ENCODER_NODE_MAP, TextEncoderKind
    except ImportError:  # pragma: no cover - direct import path
        from comfyui_text_encoder import TEXT_ENCODER_NODE_MAP, TextEncoderKind

    if text_encoder_kind is None:
        # Backward compat: caller did not supply kind (legacy or separate-load).
        use_adv = a1111_mode
    else:
        recipe = TEXT_ENCODER_NODE_MAP.get(
            text_encoder_kind,
            TEXT_ENCODER_NODE_MAP[TextEncoderKind.UNKNOWN],
        )
        use_adv = a1111_mode and recipe.supports_a1111_adv

    if use_adv:
        encode_class = "BNK_CLIPTextEncodeAdvanced"
        extra_inputs = {
            "token_normalization": "mean",
            "weight_interpretation": "A1111",
        }
    else:
        encode_class = "CLIPTextEncode"
        extra_inputs = {}

    workflow[pos_id] = {
        "class_type": encode_class,
        "inputs": {"text": prompt, "clip": clip_ref, **extra_inputs},
    }
    workflow[neg_id] = {
        "class_type": encode_class,
        "inputs": {"text": negative_prompt, "clip": clip_ref, **extra_inputs},
    }


def build_txt2img_workflow(
    prompt: str,
    negative_prompt: str = "",
    *,
    ckpt_name: str = "",
    sampler_name: str = "euler",
    scheduler: str = "normal",
    steps: int = 20,
    cfg: float = 8.0,
    width: int = 512,
    height: int = 512,
    seed: int = -1,
    batch_size: int = 1,
    vae_name: str = "",
    # -- Separate load (Flux/SD3/SDXL) --
    diffusion_model: str = "",
    text_encoder_1: str = "",
    text_encoder_2: str = "",
    clip_type: str = "",
    weight_dtype: str = "default",
    # -- ControlNet (optional) --
    controlnet_model: str = "",
    controlnet_strength: float = 1.0,
    controlnet_image_name: str = "",
    # -- Upscale (optional) --
    upscale_model: str = "",
    # -- LoRA (optional, daisy-chained) --
    loras: list | None = None,
    # -- Output mode --
    use_preview: bool = False,
    # -- A1111 compatible prompt weighting (requires ComfyUI_ADV_CLIP_emb) --
    a1111_mode: bool = False,
    # -- Text encoder kind for BNK dispatch (None = backward compat) --
    text_encoder_kind=None,   # TextEncoderKind | None
) -> dict:
    """Build a txt2img workflow with optional separate-load, ControlNet,
    and upscale support.

    Node layout (checkpoint mode):
        4: CheckpointLoaderSimple  ->  6: CLIPTextEncode (positive)
                                   ->  7: CLIPTextEncode (negative)
        5: EmptyLatentImage
        3: KSampler (connects model/positive/negative/latent)
        8: VAEDecode
        9: SaveImage

    Separate-load mode (Flux/SD3) replaces node 4 with:
        11: UNETLoader, 12: DualCLIPLoader or CLIPLoader, 10: VAELoader

    Optional nodes:
        10: VAELoader (also used in checkpoint mode when vae_name set)
        20-22: ControlNet (ControlNetLoader, LoadImage, ControlNetApplyAdvanced)
        30-31: Upscale (UpscaleModelLoader, ImageUpscaleWithModel)

    Parameters
    ----------
    seed:
        -1 means random. A random seed will be generated automatically.

    Returns
    -------
    dict
        ComfyUI API format workflow (node_id -> node definition).
    """
    if seed < 0:
        seed = random.randint(0, 2**32 - 1)

    # Lazy import — avoids circular dependency at module level.
    try:
        from .comfyui_text_encoder import TextEncoderKind as _TEK
    except ImportError:  # pragma: no cover - direct import path
        from comfyui_text_encoder import TextEncoderKind as _TEK
    # True when the caller confirmed a Wan/QWEN3 text encoder.
    _is_qwen3 = text_encoder_kind is not None and text_encoder_kind == _TEK.QWEN3

    use_separate = bool(diffusion_model)
    vae_ref = ["4", 2]  # default: CheckpointLoaderSimple slot 2
    clip_ref = ["4", 1]
    model_ref = ["4", 0]

    workflow: dict = {}

    # --- Model loading ---
    if use_separate:
        workflow["11"] = {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": diffusion_model,
                "weight_dtype": weight_dtype or "default",
            },
        }
        model_ref = ["11", 0]

        # "sdxl" was removed in newer ComfyUI; the equivalent is "stable_diffusion".
        # Wan/QWEN3 image models (Anima etc.) require clip_type="qwen_image".
        # NOTE: "wan" is a different type used for Wan video models — do NOT use for image.
        if clip_type:
            resolved_clip_type = clip_type
        elif _is_qwen3:
            resolved_clip_type = "qwen_image"
        else:
            resolved_clip_type = "stable_diffusion"
        if text_encoder_2:
            workflow["12"] = {
                "class_type": "DualCLIPLoader",
                "inputs": {
                    "clip_name1": text_encoder_1,
                    "clip_name2": text_encoder_2,
                    "type": resolved_clip_type,
                },
            }
        else:
            workflow["12"] = {
                "class_type": "CLIPLoader",
                "inputs": {
                    "clip_name": text_encoder_1,
                    "type": resolved_clip_type,
                },
            }
        clip_ref = ["12", 0]

        workflow["10"] = {
            "class_type": "VAELoader",
            "inputs": {"vae_name": vae_name},
        }
        vae_ref = ["10", 0]
    else:
        workflow["4"] = {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": ckpt_name},
        }
        if vae_name:
            workflow["10"] = {
                "class_type": "VAELoader",
                "inputs": {"vae_name": vae_name},
            }
            vae_ref = ["10", 0]

    # --- LoRA chain (optional) ---
    # In checkpoint mode: LoraLoader chains both model and clip.
    # In separate-load mode: LoraLoaderModelOnly chains only model (clip comes from dedicated loader).
    if loras:
        for i, entry in enumerate(loras):
            name = (entry or {}).get("name") if isinstance(entry, dict) else None
            if not name:
                continue
            strength_model = float((entry or {}).get("strength_model", 1.0))
            strength_clip = float((entry or {}).get("strength_clip", strength_model))
            nid = str(40 + i)
            if use_separate:
                workflow[nid] = {
                    "class_type": "LoraLoaderModelOnly",
                    "inputs": {
                        "model": model_ref,
                        "lora_name": name,
                        "strength_model": strength_model,
                    },
                }
                model_ref = [nid, 0]
            else:
                workflow[nid] = {
                    "class_type": "LoraLoader",
                    "inputs": {
                        "model": model_ref,
                        "clip": clip_ref,
                        "lora_name": name,
                        "strength_model": strength_model,
                        "strength_clip": strength_clip,
                    },
                }
                model_ref = [nid, 0]
                clip_ref = [nid, 1]

    # --- CLIP text encoding ---
    add_clip_encode_pair(
        workflow, prompt, negative_prompt, clip_ref,
        a1111_mode=a1111_mode,
        text_encoder_kind=text_encoder_kind,
    )

    positive_ref = ["6", 0]
    negative_ref = ["7", 0]

    # --- ControlNet (optional) ---
    if controlnet_model and controlnet_image_name:
        workflow["20"] = {
            "class_type": "ControlNetLoader",
            "inputs": {"control_net_name": controlnet_model},
        }
        workflow["21"] = {
            "class_type": "LoadImage",
            "inputs": {"image": controlnet_image_name},
        }
        workflow["22"] = {
            "class_type": "ControlNetApplyAdvanced",
            "inputs": {
                "positive": positive_ref,
                "negative": negative_ref,
                "control_net": ["20", 0],
                "image": ["21", 0],
                "strength": controlnet_strength,
                "start_percent": 0.0,
                "end_percent": 1.0,
            },
        }
        positive_ref = ["22", 0]
        negative_ref = ["22", 1]

    # --- Latent ---
    # Anima/Wan image models use a standard 4-channel latent (EmptyLatentImage).
    # EmptySD3LatentImage (16ch) is NOT used for Wan image — verified against native workflow.
    workflow["5"] = {
        "class_type": "EmptyLatentImage",
        "inputs": {
            "width": width,
            "height": height,
            "batch_size": batch_size,
        },
    }

    workflow["3"] = {
        "class_type": "KSampler",
        "inputs": {
            "model": model_ref,
            "positive": positive_ref,
            "negative": negative_ref,
            "latent_image": ["5", 0],
            "seed": seed,
            "steps": steps,
            "cfg": cfg,
            "sampler_name": sampler_name,
            "scheduler": scheduler,
            "denoise": 1.0,
        },
    }

    # --- VAE Decode ---
    workflow["8"] = {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["3", 0], "vae": vae_ref},
    }

    image_source = ["8", 0]

    # --- Upscale (optional) ---
    if upscale_model:
        workflow["30"] = {
            "class_type": "UpscaleModelLoader",
            "inputs": {"model_name": upscale_model},
        }
        workflow["31"] = {
            "class_type": "ImageUpscaleWithModel",
            "inputs": {
                "upscale_model": ["30", 0],
                "image": image_source,
            },
        }
        image_source = ["31", 0]

    # --- Save ---
    # Use PreviewImage when the caller manages saving externally (no output/ residue).
    if use_preview:
        workflow["9"] = {
            "class_type": "PreviewImage",
            "inputs": {"images": image_source},
        }
    else:
        workflow["9"] = {
            "class_type": "SaveImage",
            "inputs": {
                "images": image_source,
                "filename_prefix": "ComfyUI",
            },
        }

    return workflow
