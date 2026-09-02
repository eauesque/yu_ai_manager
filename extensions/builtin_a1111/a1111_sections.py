"""on_build_sections implementation for builtin-a1111.

Produces DetailSection list from parsed_fields for the collect-mode hook
introduced in the inspect/modal unification plan.
A1111 does not have a workflow graph, so only LoRA and Embedding sections
are produced (both derived from the positive prompt text).
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

from extensions.builtin_a1111 import A1111_META_SOURCES  # noqa: E402


def on_build_sections_impl(
    file_row: dict[str, Any],
    raw_meta_json: str | None,
    parsed_fields: dict[str, Any],
) -> list[DetailSection] | None:
    """Return DetailSection list for A1111 files, or None if not applicable."""
    meta_source: str | None = file_row.get("meta_source")
    if meta_source not in A1111_META_SOURCES:
        return None

    positive: str | None = parsed_fields.get("positive")
    if not positive:
        return None

    # Import locally to avoid circular deps at module level
    from a1111_parser_parse import extract_embeddings, extract_loras  # noqa: PLC0415

    sections: list[DetailSection] = []

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

    embeddings = extract_embeddings(positive)
    if embeddings:
        sections.append(
            DetailSection(
                title="Embedding",
                display_type="table",
                content=embeddings,
                copyable=False,
            )
        )

    return sections if sections else None
