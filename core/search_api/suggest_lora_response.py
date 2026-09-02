"""LoRA suggestion response builder."""

import re

from core.infra_core.api_params import get_int_arg, get_str_arg
from core.services_core.db_api import get_readonly_db

_LORA_RE = re.compile(r"<lora:([^:>]+):", re.IGNORECASE)


def build_suggest_lora_response(args):
    """LoRA name suggestion: collect <lora:NAME:weight> references from raw_prompt and return."""
    q = get_str_arg(args, ("q", "query"), "")
    limit = get_int_arg(args, ("limit", "n"), 20, minimum=1, maximum=50)

    con = get_readonly_db()
    q_lower = q.strip().lower()
    if q_lower:
        # Filter candidates with LIKE first, then apply prefix match on Python side
        q_like = q_lower.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = con.execute(
            "SELECT raw_prompt FROM templates "
            "WHERE raw_prompt LIKE ? ESCAPE '\\' LIMIT 5000",
            (f"%<lora:{q_like}%",),
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT raw_prompt FROM templates "
            "WHERE raw_prompt LIKE '%<lora:%' LIMIT 5000"
        ).fetchall()
    # pooled connection: do not close

    seen: set = set()
    suggestions = []

    for row in rows:
        raw = row["raw_prompt"] or ""
        for m in _LORA_RE.finditer(raw):
            name = m.group(1).strip()
            if not name:
                continue
            if q_lower and not name.lower().startswith(q_lower):
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            suggestions.append(name)
            if len(suggestions) >= limit:
                break
        if len(suggestions) >= limit:
            break

    suggestions.sort(key=str.lower)
    return {"q": q, "suggestions": suggestions[:limit]}
