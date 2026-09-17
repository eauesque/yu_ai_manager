"""Emphasis weight constants shared between sd_nai_core and prompt_sim_core.

Base emphasis constants used in both SD and NAI prompt syntax.
Placed as an independent shared module to avoid circular dependencies.
"""

import re

SD_BASE = 1.1
NAI_BASE = 1.05

# ── Regex building blocks for prompt weight values ──────────────
# Use these in f-strings or re.compile() to ensure consistent matching
# of weight numbers like 1.2, 0.8, .8, -.5 across all modules.

#: Unsigned weight: matches "1.2", "0.8", ".8", "42"
W_NUM = r"\d*\.?\d+"

#: Signed weight: matches "-1.2", "-.8", "0.8", ".5"
W_SNUM = r"-?\d*\.?\d+"

# ── Pre-compiled patterns for common prompt syntax ──────────────

#: SD weighted emphasis: (text:weight)
SD_WEIGHT_RE = re.compile(rf"\(([^()]+):({W_NUM})\)")

#: NAI weighted emphasis: weight::text::
NAI_WEIGHT_RE = re.compile(rf"({W_SNUM})::((?:[^:]|:[^:])+?)::")

#: SD alternation / prompt editing: [from:to:step]
SD_ALTERNATION_RE = re.compile(rf"\[[^\[\]]*:[^\[\]]*:{W_NUM}\]")
