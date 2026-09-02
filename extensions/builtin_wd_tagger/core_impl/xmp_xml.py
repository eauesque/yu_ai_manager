"""WD-Tagger XMP construction helpers.

The legacy ``build_xmp_packet`` returns a complete XMP XML string and is kept
for backward compatibility — callers that already pair it with
``write_xmp_to_file`` keep working (the writer now parses+merges instead of
replacing). New code should prefer :func:`write_wdtag_metadata`, which goes
straight from typed inputs to a per-namespace merge with no intermediate
string serialization.
"""

from __future__ import annotations

import time

from core.tools.xmp import merge_into_file
from core.tools.xmp.packet import XmpData, serialize


def build_wdtag_attrs(
    *,
    model: str,
    general_threshold: float = 0.35,
    character_threshold: float = 0.85,
    tag_count: int,
    tagged_at: int | None = None,
) -> dict[str, str]:
    """Return the ``wdtag:*`` attribute dict ready for ``merge_into_file``."""
    return {
        "model": model,
        "general_threshold": str(general_threshold),
        "character_threshold": str(character_threshold),
        "tagged_at": str(tagged_at if tagged_at is not None else int(time.time())),
        "tag_count": str(tag_count),
    }


def write_wdtag_metadata(
    image_path: str,
    *,
    tag_names: list[str],
    model: str,
    general_threshold: float = 0.35,
    character_threshold: float = 0.85,
) -> bool:
    """Merge WD-Tagger's wdtag attrs + dc:subject tags into *image_path*.

    Other namespaces already present (sweep, etc.) are preserved.
    """
    attrs = build_wdtag_attrs(
        model=model,
        general_threshold=general_threshold,
        character_threshold=character_threshold,
        tag_count=len(tag_names),
    )
    ok_attrs = merge_into_file(image_path, prefix="wdtag", attrs=attrs)
    ok_tags = merge_into_file(
        image_path, prefix="dc",
        list_items=list(tag_names), list_element_name="subject",
    )
    return ok_attrs and ok_tags


def build_xmp_packet(
    tag_names: list[str],
    model: str,
    general_threshold: float = 0.35,
    character_threshold: float = 0.85,
) -> str:
    """Build a complete XMP XML packet (legacy callers + tests).

    Equivalent in content to the previous template-based implementation but
    routed through :mod:`core.tools.xmp.packet` for consistency.
    """
    data = XmpData()
    data.attrs["wdtag"] = build_wdtag_attrs(
        model=model,
        general_threshold=general_threshold,
        character_threshold=character_threshold,
        tag_count=len(tag_names),
    )
    data.list_items["dc"] = list(tag_names)
    data.list_element_name["dc"] = "subject"
    return serialize(data)
