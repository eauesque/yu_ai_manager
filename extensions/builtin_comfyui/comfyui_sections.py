"""on_build_sections implementation for builtin-comfyui.

Produces DetailSection list from parsed_fields + raw_meta_json for the
collect-mode hook introduced in the inspect/modal unification plan.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

# Ensure project root and ext dir are importable when loaded as extension
_ext_dir = Path(__file__).resolve().parent
_project_root = _ext_dir.parent.parent
for _p in (str(_ext_dir), str(_project_root)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.extensions_core.runtime import DetailSection  # noqa: E402

from core.parsers.prompt_extract_special import extract_embeddings, extract_loras  # noqa: E402
from extensions.builtin_comfyui import COMFY_META_SOURCES  # noqa: E402

logger = logging.getLogger(__name__)


def on_build_sections_impl(
    file_row: dict[str, Any],
    raw_meta_json: str | None,
    parsed_fields: dict[str, Any],
) -> list[DetailSection] | None:
    """Return DetailSection list for ComfyUI files, or None if not applicable."""
    meta_source: str | None = file_row.get("meta_source")
    if meta_source not in COMFY_META_SOURCES:
        return None

    positive: str | None = parsed_fields.get("positive")
    # Require either positive text or raw workflow JSON to produce any sections
    if not positive and not raw_meta_json:
        return None

    sections: list[DetailSection] = []

    # -- LoRA / Embedding from positive prompt --------------------------------
    if positive:
        loras = extract_loras(positive)
        if loras:
            sections.append(
                DetailSection(
                    title="LoRA",
                    display_type="table",
                    content=loras,
                    copyable=False,
                )
            )
        embeds = extract_embeddings(positive)
        if embeds:
            sections.append(
                DetailSection(
                    title="Embedding",
                    display_type="table",
                    content=embeds,
                    copyable=False,
                )
            )

    # -- All Positive Prompts (multi-node) ------------------------------------
    # Re-parse the workflow JSON only for things parsed_fields doesn't cover:
    # the full list of CLIPTextEncode positive texts (parsed_fields only has [0]).
    if raw_meta_json:
        try:
            obj = json.loads(raw_meta_json)
        except (json.JSONDecodeError, ValueError):
            obj = None

        if obj is not None and isinstance(obj, dict):
            # Try to extract multi-positive from workflow via shared helper
            try:
                from core.extract_core.comfyui_extract_helpers import find_clip_texts  # noqa: PLC0415
                pos_texts, _ = find_clip_texts(obj)
                if len(pos_texts) > 1:
                    sections.append(
                        DetailSection(
                            title="All Positive Prompts",
                            display_type="list",
                            content=[{"index": i, "text": t} for i, t in enumerate(pos_texts)],
                            copyable=True,
                        )
                    )
            except Exception:  # noqa: BLE001
                logger.debug("optional ComfyUI section could not be built", exc_info=True)

            # -- Workflow JSON ------------------------------------------------
            sections.append(
                DetailSection(
                    title="Workflow JSON",
                    display_type="json",
                    content=obj,
                    copyable=True,
                )
            )

    return sections if sections else None
