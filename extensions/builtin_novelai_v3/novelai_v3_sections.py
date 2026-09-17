"""on_build_sections implementation for builtin-novelai-v3.

Produces DetailSection list for the collect-mode hook introduced in the
inspect/modal unification plan.  The legacy NovelAI v3 format does not use
<lora:> syntax and has no workflow graph, so this implementation returns None
unless parsed_fields carries recognisable prompts with extractable extras.
"""

from __future__ import annotations

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
from extensions.builtin_novelai_v3 import NAI_V3_META_SOURCES  # noqa: E402


def on_build_sections_impl(
    file_row: dict[str, Any],
    raw_meta_json: str | None,
    parsed_fields: dict[str, Any],
) -> list[DetailSection] | None:
    """Return DetailSection list for legacy NovelAI v3 files, or None if not applicable."""
    meta_source: str | None = file_row.get("meta_source")
    if meta_source not in NAI_V3_META_SOURCES:
        return None

    positive: str | None = parsed_fields.get("positive")
    if not positive:
        return None

    sections: list[DetailSection] = []

    # NAI v3 legacy format does not normally use <lora:> syntax, but we still
    # check for completeness / future-proofing.
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

    return sections if sections else None
