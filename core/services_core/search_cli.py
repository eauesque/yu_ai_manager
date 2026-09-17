"""CLI search -- build_tag_filter_sql, cmd_search"""

import re
from typing import Any

from core.helpers_core.helpers_text_path import norm_space, split_namespace


def build_tag_filter_sql(q: str | None) -> tuple[str, list[Any]]:
    """Minimal query builder.

    - Whitespace-delimited tokens are ANDed
    - OR is supported in a simplified manner (not strict)
    - -tag for NOT
    - artist:foo style namespace support

    Note: intended to be enhanced later
    """
    if not q:
        return "1=1", []

    tokens = [t for t in re.split(r"\s+", q.strip()) if t]

    # Handle OR in a simplified manner
    seg: list[str] = []
    or_segs: list[list[str]] = []
    for t in tokens:
        if t.upper() == "OR":
            if seg:
                or_segs.append(seg)
                seg = []
        else:
            seg.append(t)
    if seg:
        or_segs.append(seg)

    def term_sql(term: str) -> tuple[str, list[Any]]:
        neg = term.startswith("-")
        term2 = term[1:] if neg else term
        ns, val = split_namespace(term2)
        val = norm_space(val)
        if ns:
            sql = (
                "EXISTS(SELECT 1 FROM file_tags ft JOIN tags t ON t.id=ft.tag_id "
                "WHERE ft.file_id=f.id AND t.namespace=? AND t.tag=?)"
            )
            ps = [ns.lower(), val.lower()]
        else:
            sql = (
                "EXISTS(SELECT 1 FROM file_tags ft JOIN tags t ON t.id=ft.tag_id "
                "WHERE ft.file_id=f.id AND t.tag=?)"
            )
            ps = [val.lower()]
        if neg:
            sql = "NOT (" + sql + ")"
        return sql, ps

    clauses: list[str] = []
    params: list[Any] = []

    if len(or_segs) == 1:
        for t in or_segs[0]:
            s, ps = term_sql(t)
            clauses.append(s)
            params.extend(ps)
        return " AND ".join(clauses) if clauses else "1=1", params

    or_clause_parts: list[str] = []
    for branch in or_segs:
        b_parts: list[str] = []
        b_params: list[Any] = []
        for t in branch:
            s, ps = term_sql(t)
            b_parts.append(s)
            b_params.extend(ps)
        or_clause_parts.append("(" + " AND ".join(b_parts) + ")")
        params.extend(b_params)

    return "(" + " OR ".join(or_clause_parts) + ")", params


