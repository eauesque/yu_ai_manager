"""PNG metadata format matching helpers from parsed chunks."""

import json
from typing import Any


def _empty_result() -> dict[str, Any]:
    return {
        "meta_source": None,
        "format": None,
        "raw_prompt": None,
        "raw_negative": None,
        "raw_meta_json": None,
        "success": False,
    }


def match_png_chunks(chunks: dict[str, str]) -> dict[str, Any]:
    result = _empty_result()

    if "Description" in chunks or "Comment" in chunks:
        desc = chunks.get("Description", "")
        comment = chunks.get("Comment", "")
        is_v4 = False
        if comment:
            try:
                comment_data = json.loads(comment)
                if isinstance(comment_data, dict) and "v4_prompt" in comment_data:
                    is_v4 = True
            except (json.JSONDecodeError, TypeError):
                pass

        if is_v4:
            raw_json = json.dumps({"Comment": comment, "Description": desc})
            result["meta_source"] = "novelai_v4_png"
            result["format"] = "novelai_v4"
            result["raw_prompt"] = desc
            result["raw_meta_json"] = raw_json
            result["success"] = True
            return result

        if desc or comment:
            result["meta_source"] = "novelai_png"
            result["format"] = "novelai"
            result["raw_prompt"] = desc or comment
            if comment:
                result["raw_meta_json"] = json.dumps({"Comment": comment, "Description": desc})
            result["success"] = True
            return result

    if "parameters" in chunks:
        result["meta_source"] = "a1111_png"
        result["format"] = "a1111"
        result["raw_prompt"] = chunks["parameters"]
        result["success"] = True
        return result

    gen_data_raw = chunks.get("generation_data", "")
    if gen_data_raw:
        gen_data_raw = gen_data_raw.rstrip("\x00").strip()
        try:
            gen_data = json.loads(gen_data_raw)
            if isinstance(gen_data, dict) and "prompt" in gen_data:
                result["meta_source"] = "tensor_art"
                result["format"] = "tensor_art"
                result["raw_prompt"] = gen_data.get("prompt", "")
                result["raw_negative"] = gen_data.get("negativePrompt", "")
                result["raw_meta_json"] = gen_data_raw
                result["success"] = True
                return result
        except (json.JSONDecodeError, TypeError):
            pass

    if "prompt" in chunks:
        result["meta_source"] = "comfyui"
        result["format"] = "comfyui"
        result["raw_meta_json"] = chunks["prompt"]
        result["success"] = True
        return result

    return result
