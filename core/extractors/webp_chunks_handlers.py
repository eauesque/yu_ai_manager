"""Chunk-specific handlers for WebP metadata extraction."""

import json
import re

from core.extractors.exif_user_comment import _parse_exif_user_comment
from core.extractors.yu_meta import unwrap_yu_meta


def handle_exif_chunk(data: bytes, out: dict[str, str]) -> None:
    uc = _parse_exif_user_comment(data)
    if uc:
        out["exif:UserComment"] = uc
        # YU_META JSON envelope (yu_ai_manager bridge save). Must be
        # unwrapped before the heuristic below, because the JSON value
        # carries "Steps:"/"Negative prompt:" substrings that would
        # otherwise cause the entire YU_META:{...} blob to be stored as
        # the raw A1111 parameters chunk.
        inner = unwrap_yu_meta(uc)
        if inner is not None:
            for k, v in inner.items():
                out.setdefault(k, v)
            return
        if ("Steps:" in uc) and ("Negative prompt:" in uc or "Sampler:" in uc):
            out.setdefault("parameters", uc)
            out.setdefault("Parameters", uc)
        else:
            merge_novelai_user_comment(uc, out)
        return

    for encoding in ("utf-8", "utf-16"):
        try:
            text = data.decode(encoding, errors="ignore").strip()
            if len(text) > 10 and ("Steps:" in text or "Negative prompt:" in text):
                out["exif:raw"] = text
                if "Steps:" in text:
                    out.setdefault("parameters", text)
                    out.setdefault("Parameters", text)
                return
        except Exception:  # noqa: S112 -- scanning chunks; a failure means this chunk is not the one
            continue


def merge_novelai_user_comment(raw_text: str, out: dict[str, str]) -> None:
    try:
        uc_obj = json.loads(raw_text)
    except (json.JSONDecodeError, TypeError):
        return
    if not isinstance(uc_obj, dict):
        return

    if "Description" in uc_obj:
        out.setdefault("Description", uc_obj["Description"])
    if "Comment" in uc_obj:
        out.setdefault("Comment", uc_obj["Comment"])
        out["nai_json"] = raw_text
        try:
            inner = json.loads(uc_obj["Comment"])
            if isinstance(inner, dict):
                if "prompt" in inner:
                    out.setdefault("prompt", inner["prompt"])
                if "uc" in inner:
                    out.setdefault("negative", inner["uc"])
        except (json.JSONDecodeError, TypeError):
            pass


def handle_xmp_chunk(data: bytes, out: dict[str, str]) -> None:
    try:
        xmp_text = data.decode("utf-8", errors="ignore").strip()
        if not xmp_text:
            return
        out["xmp"] = xmp_text
        desc_match = re.search(
            r"<(?:dc:description|exif:UserComment)[^>]*>(.*?)</(?:dc:description|exif:UserComment)>",
            xmp_text,
            re.DOTALL,
        )
        if not desc_match:
            return
        desc = desc_match.group(1).strip()
        desc = re.sub(r"<!\\[CDATA\\[(.*?)\\]\\]>", r"\\1", desc, flags=re.DOTALL).strip()
        if not desc:
            return

        out["Description"] = desc
        if ("Steps:" in desc) and ("Negative prompt:" in desc or "Sampler:" in desc):
            out.setdefault("parameters", desc)
            out.setdefault("Parameters", desc)
    except Exception:
        return


def handle_unknown_chunk(fourcc: bytes, data: bytes, out: dict[str, str]) -> None:
    try:
        text = data.decode("utf-8", errors="ignore").strip()
        if len(text) <= 20:
            return
        if not any(kw in text for kw in ["Steps:", "Negative prompt:", "Sampler:", "prompt", "workflow"]):
            return

        chunk_name = fourcc.decode("ascii", errors="replace").strip()
        out[f"chunk:{chunk_name}"] = text
        if "Steps:" in text:
            out.setdefault("parameters", text)
            out.setdefault("Parameters", text)
        elif "prompt" in text.lower():
            out.setdefault("prompt", text)
    except Exception:
        return
