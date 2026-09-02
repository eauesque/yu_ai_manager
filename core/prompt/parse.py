import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def parse_a1111_prompt(raw_text: str) -> dict[str, Any]:
    """Split A1111 raw prompt into positive/negative/parameters."""
    # Defensive unwrap for legacy DB rows whose raw_prompt is the
    # YU_META JSON envelope (written by an older buggy chunk extractor
    # that stored the wrapper instead of the inner parameters value).
    # Lets old data work without a rescan.
    from core.extractors.yu_meta import unwrap_yu_meta
    inner = unwrap_yu_meta(raw_text)
    if inner is not None:
        inner_params = inner.get("parameters") or inner.get("Parameters")
        if isinstance(inner_params, str) and inner_params:
            raw_text = inner_params

    lines = raw_text.split('\n')
    positive_lines = []
    negative_lines = []

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("Negative prompt:") or line.startswith("Steps:"):
            break
        positive_lines.append(lines[i])
        i += 1
    positive = '\n'.join(positive_lines).strip()

    if i < len(lines) and lines[i].strip().startswith("Negative prompt:"):
        first = re.sub(r'^Negative prompt:\s*', '', lines[i].strip(), flags=re.IGNORECASE)
        if first:
            negative_lines.append(first)
        i += 1
        while i < len(lines) and not lines[i].strip().startswith("Steps:"):
            negative_lines.append(lines[i].strip())
            i += 1
    negative = '\n'.join(negative_lines).strip()

    parameters = {}
    if i < len(lines):
        param_line = lines[i].strip()
        if param_line.startswith("Steps:"):
            parts = [p.strip() for p in param_line.split(',') if p.strip()]
            for part in parts:
                if ':' in part:
                    key, value = part.split(':', 1)
                    parameters[key.strip()] = value.strip()

    return {"positive": positive, "negative": negative, "parameters": parameters}


def parse_novelai_v4_metadata(raw_meta_json: str) -> dict[str, Any] | None:
    """Parse NovelAI V4 metadata JSON."""
    try:
        outer = json.loads(raw_meta_json)
        if not isinstance(outer, dict) or "Comment" not in outer:
            return None
        data = json.loads(outer["Comment"])
        result = {
            "base_caption": "",
            "character_prompts": [],
            "negative_base": "",
            "negative_characters": [],
            "parameters": {},
            "vibe_transfer": None,
        }

        if "v4_prompt" in data:
            v4_pos = data["v4_prompt"]
            caption = v4_pos.get("caption", {})
            result["base_caption"] = caption.get("base_caption", "")
            for char in caption.get("char_captions", []):
                result["character_prompts"].append({"prompt": char.get("char_caption", ""), "positions": char.get("centers", [])})

        if "v4_negative_prompt" in data:
            v4_neg = data["v4_negative_prompt"]
            caption = v4_neg.get("caption", {})
            result["negative_base"] = caption.get("base_caption", "")
            for char in caption.get("char_captions", []):
                result["negative_characters"].append({"prompt": char.get("char_caption", ""), "positions": char.get("centers", [])})

        params = {}
        if data.get("steps"):
            params["Steps"] = str(data["steps"])
        if data.get("sampler"):
            params["Sampler"] = data["sampler"]
        if data.get("scale"):
            params["CFG scale"] = str(data["scale"])
        # Seed 0 is a legitimate seed, so test for presence rather than truth.
        if data.get("seed") is not None:
            params["Seed"] = str(data["seed"])
        if data.get("width") and data.get("height"):
            params["Size"] = f"{data['width']}x{data['height']}"
        if data.get("noise_schedule"):
            params["Noise Schedule"] = data["noise_schedule"]
        if data.get("sm"):
            params["SMEA"] = "Enabled" if data["sm"] else "Disabled"
        if data.get("sm_dyn"):
            params["SMEA DYN"] = "Enabled" if data["sm_dyn"] else "Disabled"
        if data.get("cfg_rescale"):
            params["CFG Rescale"] = str(data["cfg_rescale"])
        result["parameters"] = params

        if data.get("director_reference_strengths"):
            vibe_desc = data.get("director_reference_descriptions", [])
            desc_text = ""
            if vibe_desc and len(vibe_desc) > 0:
                caption = vibe_desc[0].get("caption", {})
                desc_text = caption.get("base_caption", "")
            result["vibe_transfer"] = {
                "strength": data["director_reference_strengths"][0] if data["director_reference_strengths"] else 0,
                "description": desc_text,
                "info_extracted": data.get("director_reference_information_extracted", [None])[0],
            }
        return result
    except Exception as e:
        logger.warning(f"NovelAI V4 parse error: {e}")
        return None
