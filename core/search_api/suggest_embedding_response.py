"""Embedding / Hypernetwork suggestion response builder."""

import re

from core.infra_core.api_params import get_int_arg, get_str_arg
from core.services_core.db_api import get_readonly_db

_EMBED_RE = re.compile(
    r"(?:<embedding:|<hypernet:|\(embedding:|(?<![<(])embedding:)"
    r"([A-Za-z0-9_\-.]+)",
    re.IGNORECASE,
)


def build_suggest_embedding_response(args):
    """Embedding name suggestion: collect embedding/hypernet references from raw_prompt and return."""
    q = get_str_arg(args, ("q", "query"), "")
    limit = get_int_arg(args, ("limit", "n"), 20, minimum=1, maximum=50)

    con = get_readonly_db()
    q_lower = q.strip().lower()
    if q_lower:
        q_like = q_lower.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = con.execute(
            "SELECT raw_prompt FROM templates "
            "WHERE (raw_prompt LIKE ? ESCAPE '\\' "
            "   OR raw_prompt LIKE ? ESCAPE '\\') LIMIT 5000",
            (f"%embedding:{q_like}%", f"%hypernet:{q_like}%"),
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT raw_prompt FROM templates "
            "WHERE raw_prompt LIKE '%embedding:%' "
            "   OR raw_prompt LIKE '%hypernet:%' LIMIT 5000"
        ).fetchall()

    seen: set = set()
    suggestions = []

    for row in rows:
        raw = row["raw_prompt"] or ""
        for m in _EMBED_RE.finditer(raw):
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
