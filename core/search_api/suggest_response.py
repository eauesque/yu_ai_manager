"""Suggest response builder."""

from core.infra_core.api_params import get_int_arg, get_str_arg
from core.services_core.db_api import get_readonly_db


def build_suggest_response(args):
    q = get_str_arg(args, ("q", "query"), "")
    limit = get_int_arg(args, ("limit", "n"), 20, minimum=1, maximum=50)
    if not q:
        return {"q": q, "suggestions": []}

    con = get_readonly_db()
    q_like = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    rows = con.execute(
        """SELECT DISTINCT tag FROM tags
           WHERE tag LIKE ? ESCAPE '\\'
           ORDER BY length(tag) ASC, tag ASC
           LIMIT ?""",
        (q_like + "%", limit * 2),
    )
    seen = set()
    suggestions = []
    for row in rows:
        normalized = row["tag"].replace(",", ", ").replace("  ", " ").strip()
        if normalized in seen:
            continue
        seen.add(normalized)
        suggestions.append(normalized)
        if len(suggestions) >= limit:
            break
    return {"q": q, "suggestions": suggestions}
