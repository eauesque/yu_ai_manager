"""Recent-window fast path for broad prompt searches."""

from core.prompt import normalize_tag_for_search, parse_tag_query
from core.query.filters_tags_resolve import resolve_tag_ids
from core.query.fts_like_helpers import path_fts_match_phrase
from core.search_api.search_rows import rows_to_results


def _resolve_prompt_fast_tag_ids(con, tag: str, case_sensitive: bool) -> list[int] | None:
    variants = [tag] if case_sensitive else normalize_tag_for_search(tag)
    tag_ids: set[int] = set()
    for variant in variants:
        ids = resolve_tag_ids(con, variant, case_sensitive)
        if ids is None:
            return None
        tag_ids.update(int(tag_id) for tag_id in ids)
    return sorted(tag_ids)


def _can_use_recent_prompt_fast_path(p: dict, keyset_info) -> bool:
    prompt_term = (p.get("in_prompt") or "").strip()
    negative_term = (p.get("in_negative") or "").strip()
    if not (bool(prompt_term) ^ bool(negative_term)):
        return False
    if keyset_info is not None or p.get("sort_by") not in ("date", "date_new"):
        return False
    if int(p.get("offset") or 0) > 5000:
        return False
    if p.get("in_prompt_regex"):
        return False
    if len(prompt_term or negative_term) < 3:
        return False
    if p.get("tag_query_regex"):
        return False
    tags = parse_tag_query(p.get("tag_query") or "")
    if sum(1 for tag in tags if not tag.startswith("-")) > 1:
        return False
    return not any(
        [
            p.get("artist"),
            p.get("from_date"),
            p.get("to_date"),
            p.get("from_ts_int"),
            p.get("to_ts_int"),
            p.get("in_char_negative"),
            p.get("in_char_positive"),
            p.get("checkpoint_filter"),
            p.get("in_path"),
            p.get("or_tags"),
            p.get("file_format") != "all",
            p.get("format_exts"),
            p.get("model_filter") != "all",
            p.get("fav_only", False),
            p.get("collection_id", 0) != 0,
            p.get("ai_analyzed", False),
            p.get("has_tags", False),
            p.get("has_annotation", False),
            p.get("has_sweep", False),
            p.get("min_rating") is not None,
            p.get("max_rating") is not None,
            p.get("min_width_int") is not None,
            p.get("max_width_int") is not None,
            p.get("min_height_int") is not None,
            p.get("max_height_int") is not None,
        ]
    )


def _try_recent_prompt_fast_path(con, p: dict, keyset_info):
    """Return top-N prompt matches by walking newest files first.

    FTS-first remains the fallback for sparse terms. This path is only for
    broad/common prompt terms where a small recent window already contains a
    full page, avoiding a 200K-row FTS result sort.
    """
    if not _can_use_recent_prompt_fast_path(p, keyset_info):
        return None

    prompt_term = (p.get("in_prompt") or "").strip()
    negative_term = (p.get("in_negative") or "").strip()
    column = "raw_prompt" if prompt_term else "raw_negative"
    needle = (prompt_term or negative_term).lower()
    case_sensitive = bool(p.get("tag_query_case_sensitive"))
    positive_tag = None
    excluded_ids: list[int] = []
    for tag in parse_tag_query(p.get("tag_query") or ""):
        if tag.startswith("-"):
            ids = _resolve_prompt_fast_tag_ids(con, tag[1:], case_sensitive)
            if ids is None:
                return None
            excluded_ids.extend(ids)
        else:
            positive_tag = tag

    where_parts = ["f.is_deleted=0"]
    params: list = []
    if positive_tag:
        positive_ids = _resolve_prompt_fast_tag_ids(con, positive_tag, case_sensitive)
        if positive_ids is None:
            return None
        path_phrase = path_fts_match_phrase(positive_tag) if p.get("also_path") else None
        positive_parts = []
        if positive_ids:
            placeholders = ",".join("?" * len(positive_ids))
            positive_parts.append(
                "EXISTS(SELECT 1 FROM file_tags "
                f"WHERE file_id=f.id AND tag_id IN ({placeholders}))"
            )
            params.extend(positive_ids)
        if path_phrase is not None:
            positive_parts.append("f.id IN (SELECT rowid FROM files_path_fts WHERE path MATCH ?)")
            params.append(path_phrase)
        if not positive_parts:
            return [], False
        where_parts.append("(" + " OR ".join(positive_parts) + ")")
    if excluded_ids:
        excluded_ids = sorted(set(excluded_ids))
        placeholders = ",".join("?" * len(excluded_ids))
        where_parts.append(
            "NOT EXISTS(SELECT 1 FROM file_tags "
            f"WHERE file_id=f.id AND tag_id IN ({placeholders}))"
        )
        params.extend(excluded_ids)

    target = p["offset"] + p["limit"] + 1
    window = max(200, min(max(target * 4, 200), 2000))
    max_window = max(64000, target)

    while window <= max_window:
        cursor = con.execute(
            "SELECT f.id, f.path, f.mtime, f.meta_source, "
            "tm.raw_prompt, tm.raw_negative "
            "FROM files f INDEXED BY idx_files_deleted_mtime "
            "CROSS JOIN templates tm ON tm.file_id=f.id "
            f"WHERE {' AND '.join(where_parts)} "
            "ORDER BY f.mtime DESC, f.id DESC LIMIT ?",
            [*params, window],
        )
        row_count = 0
        matched = []
        for row in cursor:
            row_count += 1
            if needle in ((row[column] or "").lower()):
                matched.append(row)
        if row_count == 0:
            return [], False
        if len(matched) >= target:
            page_rows = matched[p["offset"]: p["offset"] + p["limit"]]
            return rows_to_results(page_rows), len(matched) > p["offset"] + p["limit"]
        if row_count < window:
            if len(matched) > p["offset"]:
                page_rows = matched[p["offset"]: p["offset"] + p["limit"]]
                return rows_to_results(page_rows), len(matched) > p["offset"] + p["limit"]
            break
        window *= 2
    return None
