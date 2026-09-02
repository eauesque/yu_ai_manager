"""on_build_sections implementation for builtin-novelai-v4.

Produces DetailSection list from parsed_fields for the collect-mode hook
introduced in the inspect/modal unification plan.

parsed_fields["novelai_v4_data"] already contains character_prompts and
vibe_transfer parsed by resolve_detail_fields().  We use that directly
without re-parsing raw_meta_json, as specified in the hook contract.

Sections produced (when data is available):
- "V4 Characters (Positive)" — character prompt list
- "V4 Characters (Negative)" — character negative list
- "Reference Images" (Vibe Transfer) — strength table
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

from extensions.builtin_novelai_v4 import NAI_V4_META_SOURCES  # noqa: E402


def on_build_sections_impl(
    file_row: dict[str, Any],
    raw_meta_json: str | None,
    parsed_fields: dict[str, Any],
) -> list[DetailSection] | None:
    """Return DetailSection list for NovelAI v4 files, or None if not applicable."""
    meta_source: str | None = file_row.get("meta_source")
    if meta_source not in NAI_V4_META_SOURCES:
        return None

    nai_v4: dict[str, Any] | None = parsed_fields.get("novelai_v4_data")
    if not nai_v4:
        return None

    sections: list[DetailSection] = []

    # -- V4 Character Prompts (Positive) -------------------------------------
    char_positives: list[dict[str, str]] = nai_v4.get("character_prompts", [])
    if char_positives:
        sections.append(
            DetailSection(
                title="V4 Characters (Positive)",
                display_type="list",
                content=char_positives,
                copyable=True,
            )
        )

    # -- V4 Character Prompts (Negative) -------------------------------------
    neg_chars: list[str] = nai_v4.get("negative_characters", [])
    if neg_chars:
        sections.append(
            DetailSection(
                title="V4 Characters (Negative)",
                display_type="list",
                content=[{"prompt": nc} for nc in neg_chars],
                copyable=True,
            )
        )

    # -- Vibe Transfer (Reference Images) ------------------------------------
    vibe: list[dict[str, Any]] = nai_v4.get("vibe_transfer", [])
    if vibe:
        sections.append(
            DetailSection(
                title="Reference Images",
                display_type="table",
                content=[
                    {"index": i, "strength": v.get("information_extracted", "?")}
                    for i, v in enumerate(vibe)
                ],
            )
        )

    return sections if sections else None
