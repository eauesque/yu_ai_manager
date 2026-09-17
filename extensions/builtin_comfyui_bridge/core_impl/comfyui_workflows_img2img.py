"""ComfyUI img2img workflow builder (Simple mode).

Builds a workflow with LoadImage + VAEEncode driving the KSampler latent input
at a configurable denoise strength. Self-contained — does not depend on the
txt2img builder so the existing txt2img code path stays untouched.

Out of scope (TODO): ControlNet integration, Upscale post-process, ImageScale
resize, inpainting/masking, batch img2img.
"""

from __future__ import annotations

import random

try:
    from .comfyui_workflows import add_clip_encode_pair
except ImportError:  # pragma: no cover - top-level extension import path
    from comfyui_workflows import add_clip_encode_pair


def _build_model_loaders(
    workflow: dict,
    *,
    ckpt_name: str,
    vae_name: str,
    diffusion_model: str,
    text_encoder_1: str,
    text_encoder_2: str,
    clip_type: str,
    weight_dtype: str,
    text_encoder_kind=None,  # TextEncoderKind | None
) -> tuple[list, list, list, bool]:
    """Build model/CLIP/VAE loader nodes. Returns (model_ref, clip_ref, vae_ref, use_separate)."""
    use_separate = bool(diffusion_model)
    model_ref: list = ["4", 0]
    clip_ref: list = ["4", 1]
    vae_ref: list = ["4", 2]

    if use_separate:
        workflow["11"] = {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": diffusion_model,
                "weight_dtype": weight_dtype or "default",
            },
        }
        model_ref = ["11", 0]

        # Wan/QWEN3 image models (Anima etc.) require clip_type="qwen_image".
        # NOTE: "wan" is a different type used for Wan video models — do NOT use for image.
        try:
            from .comfyui_text_encoder import TextEncoderKind as _TEK
        except ImportError:  # pragma: no cover - direct import path
            from comfyui_text_encoder import TextEncoderKind as _TEK
        _is_qwen3 = text_encoder_kind is not None and text_encoder_kind == _TEK.QWEN3
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

    return model_ref, clip_ref, vae_ref, use_separate


def _build_lora_chain(
    workflow: dict,
    model_ref: list,
    clip_ref: list,
    *,
    loras: list | None,
    use_separate: bool,
) -> tuple[list, list]:
    """Chain LoRA loaders (nodes 40+). Returns updated (model_ref, clip_ref)."""
    if not loras:
        return model_ref, clip_ref

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

    return model_ref, clip_ref


def build_img2img_workflow(
    prompt: str,
    negative_prompt: str = "",
    *,
    init_image_name: str,
    denoise: float = 0.75,
    ckpt_name: str = "",
    sampler_name: str = "euler",
    scheduler: str = "normal",
    steps: int = 20,
    cfg: float = 8.0,
    seed: int = -1,
    batch_size: int = 1,
    vae_name: str = "",
    diffusion_model: str = "",
    text_encoder_1: str = "",
    text_encoder_2: str = "",
    clip_type: str = "",
    weight_dtype: str = "default",
    loras: list | None = None,
    use_preview: bool = False,
    a1111_mode: bool = False,
    text_encoder_kind=None,  # TextEncoderKind | None; None = backward compat
) -> dict:
    """Build an img2img workflow.

    Node layout:
        4 / 11+12+10 : model loaders
        40+          : LoRA chain (optional)
        6 / 7        : CLIPTextEncode (positive/negative)
        50           : LoadImage (init image)
        51           : VAEEncode (pixels -> latent)
        3            : KSampler (denoise = clamp[0, 1])
        8            : VAEDecode
        9            : SaveImage / PreviewImage
    """
    if seed < 0:
        seed = random.randint(0, 2**32 - 1)
    denoise = max(0.0, min(1.0, float(denoise)))

    workflow: dict = {}

    model_ref, clip_ref, vae_ref, use_separate = _build_model_loaders(
        workflow,
        ckpt_name=ckpt_name,
        vae_name=vae_name,
        diffusion_model=diffusion_model,
        text_encoder_1=text_encoder_1,
        text_encoder_2=text_encoder_2,
        clip_type=clip_type,
        weight_dtype=weight_dtype,
        text_encoder_kind=text_encoder_kind,
    )

    model_ref, clip_ref = _build_lora_chain(
        workflow, model_ref, clip_ref, loras=loras, use_separate=use_separate,
    )

    add_clip_encode_pair(
        workflow, prompt, negative_prompt, clip_ref,
        a1111_mode=a1111_mode,
        text_encoder_kind=text_encoder_kind,
    )

    workflow["50"] = {
        "class_type": "LoadImage",
        "inputs": {"image": init_image_name},
    }
    workflow["51"] = {
        "class_type": "VAEEncode",
        "inputs": {"pixels": ["50", 0], "vae": vae_ref},
    }

    # batch_size > 1: replicate the encoded latent via RepeatLatentBatch.
    # VAEEncode outputs a single-image latent; without replication KSampler
    # would only generate one image regardless of the requested batch count.
    latent_ref: list = ["51", 0]
    if batch_size > 1:
        workflow["52"] = {
            "class_type": "RepeatLatentBatch",
            "inputs": {"samples": ["51", 0], "amount": batch_size},
        }
        latent_ref = ["52", 0]

    workflow["3"] = {
        "class_type": "KSampler",
        "inputs": {
            "model": model_ref,
            "positive": ["6", 0],
            "negative": ["7", 0],
            "latent_image": latent_ref,
            "seed": seed,
            "steps": steps,
            "cfg": cfg,
            "sampler_name": sampler_name,
            "scheduler": scheduler,
            "denoise": denoise,
        },
    }
    workflow["8"] = {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["3", 0], "vae": vae_ref},
    }

    if use_preview:
        workflow["9"] = {
            "class_type": "PreviewImage",
            "inputs": {"images": ["8", 0]},
        }
    else:
        workflow["9"] = {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["8", 0],
                "filename_prefix": "ComfyUI",
            },
        }

    return workflow


__all__ = ["build_img2img_workflow"]
