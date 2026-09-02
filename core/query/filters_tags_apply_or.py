from core.prompt import normalize_tag_for_search, parse_tag_query

from .filters_tags_apply_helpers import _wd_tag_candidate_sql
from .filters_tags_path import (
    path_search_has_match,
    path_search_params,
)
from .filters_tags_resolve import (
    resolve_tag_ids,
    tag_candidate_set_sql,
)
from .fts_like_helpers import path_fts_match_phrase


def apply_or_tags_filter(where_parts, params, or_tags, con=None, wd_model=None):
    if not (or_tags and or_tags.strip()):
        return
    candidate_parts = []
    candidate_params = []
    fallback_conditions = []
    fallback_params = []
    for otag in parse_tag_query(or_tags):
        if otag.startswith("-"):
            continue
        path_hit = path_search_has_match(con, otag)
        for variant in normalize_tag_for_search(otag):
            tag_ids = resolve_tag_ids(con, variant, case_sensitive=False)
            if tag_ids is not None and tag_ids:
                candidate_parts.append(tag_candidate_set_sql(tag_ids))
                candidate_params.extend(tag_ids)
            elif tag_ids is None:
                fallback_conditions.append(
                    "EXISTS(SELECT 1 FROM file_tags ft JOIN tags t ON t.id=ft.tag_id "
                    "WHERE ft.file_id=f.id AND LOWER(t.tag)=LOWER(?))"
                )
                fallback_params.append(variant)
        # Only add the path subquery when the term is long enough for the
        # trigram MATCH path (idxNum=M0). Short terms would otherwise force a
        # LIKE-with-ESCAPE full SCAN of files_path_fts.
        if path_hit is not False and path_fts_match_phrase(otag) is not None:
            candidate_parts.append("SELECT rowid AS id FROM files_path_fts WHERE path MATCH ?")
            candidate_params.extend(path_search_params(otag))
        # Also match WD-tagger tags for the active model (OR with prompt tags).
        wd = _wd_tag_candidate_sql(otag, con, wd_model)
        if wd is not None:
            wd_sql, wd_params = wd
            candidate_parts.append(wd_sql)
            candidate_params.extend(wd_params)
    if candidate_parts and not fallback_conditions:
        where_parts.append("f.id IN (" + " UNION ".join(candidate_parts) + ")")
        params.extend(candidate_params)
    elif fallback_conditions:
        where_parts.append("(" + " OR ".join(fallback_conditions) + ")")
        params.extend(fallback_params)
