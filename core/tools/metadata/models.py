"""Model name/hash extraction helpers."""

import json


def _strip_model_ext(value: str) -> str:
    return value.replace(".safetensors", "").replace(".ckpt", "")


def extract_model_info(raw_meta_json: str | None) -> tuple[str | None, str | None]:
    """Extract model name and hash from raw metadata JSON."""
    if not raw_meta_json:
        return (None, None)

    try:
        meta = json.loads(raw_meta_json)

        if "model" in meta:
            return (meta.get("model"), None)

        if "Model" in meta:
            return (meta.get("Model"), meta.get("Model hash"))

        if "prompt" in meta:
            prompt_data = meta.get("prompt", {})
            if isinstance(prompt_data, dict):
                for node_data in prompt_data.values():
                    if isinstance(node_data, dict):
                        inputs = node_data.get("inputs", {})

                        if "ckpt_name" in inputs:
                            ckpt = inputs["ckpt_name"]
                            if ckpt and isinstance(ckpt, str):
                                return (_strip_model_ext(ckpt), None)

                        if "model" in inputs:
                            model = inputs["model"]
                            if isinstance(model, str) and model.endswith((".safetensors", ".ckpt")):
                                return (_strip_model_ext(model), None)

        if "checkpoint" in meta:
            ckpt = meta["checkpoint"]
            if ckpt and isinstance(ckpt, str):
                return (_strip_model_ext(ckpt), None)

        if "ckpt_name" in meta:
            ckpt = meta["ckpt_name"]
            if ckpt and isinstance(ckpt, str):
                return (_strip_model_ext(ckpt), None)

    except (json.JSONDecodeError, TypeError):
        pass

    return (None, None)
