"""Tag id resolution helpers for count-only search."""

from __future__ import annotations

from core.prompt import normalize_tag_for_search, parse_tag_query
from core.query.filters_tags_resolve import resolve_tag_ids


def resolve_excluded_tag_ids(con, p: dict) -> list[int] | None:
    tag_ids: set[int] = set()
    for tag in parse_tag_query(p.get("tag_query") or ""):
        tag_val = tag[1:]
        variants = [tag_val] if p.get("tag_query_case_sensitive") else normalize_tag_for_search(tag_val)
        for variant in variants:
            ids = resolve_tag_ids(con, variant, bool(p.get("tag_query_case_sensitive")))
            if ids is None:
                return None
            tag_ids.update(int(tag_id) for tag_id in ids)
    return sorted(tag_ids)


def split_tag_ids(con, p: dict) -> tuple[list[int], list[int]] | None:
    positive_ids: set[int] = set()
    excluded_ids: set[int] = set()
    case_sensitive = bool(p.get("tag_query_case_sensitive"))
    for tag in parse_tag_query(p.get("tag_query") or ""):
        is_negative = tag.startswith("-")
        tag_val = tag[1:] if is_negative else tag
        variants = [tag_val] if case_sensitive else normalize_tag_for_search(tag_val)
        for variant in variants:
            ids = resolve_tag_ids(con, variant, case_sensitive)
            if ids is None:
                return None
            target = excluded_ids if is_negative else positive_ids
            target.update(int(tag_id) for tag_id in ids)
    return sorted(positive_ids), sorted(excluded_ids)


def resolve_positive_tag_ids(con, p: dict) -> list[int] | None:
    tags = parse_tag_query(p.get("tag_query") or "")
    if len(tags) != 1 or tags[0].startswith("-"):
        return None
    tag_val = tags[0]
    tag_ids: set[int] = set()
    variants = [tag_val] if p.get("tag_query_case_sensitive") else normalize_tag_for_search(tag_val)
    for variant in variants:
        ids = resolve_tag_ids(con, variant, bool(p.get("tag_query_case_sensitive")))
        if ids is None:
            return None
        tag_ids.update(int(tag_id) for tag_id in ids)
    return sorted(tag_ids)
