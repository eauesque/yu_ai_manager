"""ComfyUI KSampler and loader parameter extraction."""

from typing import Any


def extract_ksampler_params(obj: Any) -> dict[str, str]:
    params: dict[str, str] = {}
    if not isinstance(obj, dict):
        return params

    nodes = list(obj.values()) if not isinstance(obj.get("nodes"), list) else obj["nodes"]

    for node in nodes:
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type") or node.get("type") or ""
        if not isinstance(class_type, str):
            continue
        ct_lower = class_type.lower()
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue

        if "ksampler" in ct_lower and "seed" not in params:
            for key in ("seed", "steps", "cfg", "sampler_name", "scheduler", "denoise"):
                val = inputs.get(key)
                if val is not None and not isinstance(val, (list, dict)):
                    params[key] = str(val)

        if "checkpointloader" in ct_lower:
            ckpt = inputs.get("ckpt_name")
            if isinstance(ckpt, str) and ckpt:
                params.setdefault("model", ckpt)
                params.setdefault("ckpt_name", ckpt)

        if ct_lower == "unetloader":
            unet = inputs.get("unet_name")
            if isinstance(unet, str) and unet:
                params.setdefault("model", unet)
                params.setdefault("diffusion_model", unet)

        if "dualcliploader" in ct_lower:
            for ck in ("clip_name1", "clip_name2"):
                cv = inputs.get(ck)
                if isinstance(cv, str) and cv:
                    params.setdefault(ck, cv)
            # Capture clip_type (e.g. "flux", "sd3", "sdxl", "stable_diffusion")
            clip_type = inputs.get("type")
            if isinstance(clip_type, str) and clip_type:
                params.setdefault("clip_type", clip_type)

        # CLIPLoader (single CLIP for SD1.5/SDXL workflows)
        if ct_lower == "cliploader":
            clip_name = inputs.get("clip_name")
            if isinstance(clip_name, str) and clip_name:
                params.setdefault("clip_name1", clip_name)

        if "cliptextencodeflux" in ct_lower:
            guidance = inputs.get("guidance")
            if guidance is not None and not isinstance(guidance, (list, dict)):
                params.setdefault("guidance", str(guidance))

        if "vaeloader" in ct_lower:
            vae = inputs.get("vae_name")
            if isinstance(vae, str) and vae:
                params.setdefault("vae", vae)

        # EmptyLatentImage / EmptySD3LatentImage / EmptyHunyuanLatentVideo etc.
        if "emptylatent" in ct_lower or ct_lower == "emptymochilatent":
            for dim_key in ("width", "height"):
                val = inputs.get(dim_key)
                if val is not None and not isinstance(val, (list, dict)):
                    params.setdefault(dim_key, str(val))

    return params
