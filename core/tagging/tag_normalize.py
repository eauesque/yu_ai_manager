"""Tag string normalization for cross-model search matching.

Pipeline (order matters):
  1. NFKC normalize (全角英数 -> 半角、合字展開)
  2. underscore -> single space
  3. casefold (Unicode-aware case folding)
  4. collapse consecutive whitespace
  5. strip both ends

Spec: docs/superpowers/specs/2026-05-10-tagger-pluggable-models-design.md § 5.5.1

The function MUST NOT change once the `tag_name_normalized` index is built.
Any change requires a full backfill migration.
Order corrected in migration 78 (re-backfills the 6 affected compatibility codepoints).
"""
from __future__ import annotations

import re
import unicodedata

_WS_RE = re.compile(r"\s+")


def normalize_tag(tag: str) -> str:
    """Normalize a tag string for cross-model search matching.

    The output of this function is what gets stored in
    `file_wd_tags.tag_name_normalized` (Phase 2) and what is
    compared against during search.

    The function MUST NOT change once `tag_name_normalized` index
    is built (Phase 2). Any change requires a full backfill migration.
    Order corrected in migration 78 (re-backfills the 6 affected compatibility codepoints).

    CANONICAL for `wd_tag_dict.tag_name_normalized` (spec 2026-06-02 §4.7).
    Query-side search normalization uses variants from `normalize_tag_for_search()`
    and compares them with this output. Changing either side can break recall;
    run recall parity tests whenever this behavior changes.
    """
    s = unicodedata.normalize("NFKC", tag)
    s = s.replace("_", " ")
    s = s.casefold()
    s = _WS_RE.sub(" ", s)
    return s.strip()
