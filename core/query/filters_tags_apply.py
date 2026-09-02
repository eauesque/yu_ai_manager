from core.prompt import parse_tag_query
from core.query.filters_tags_apply_helpers import (
    _apply_excluded_tag,
    _apply_included_tag,
    _apply_regex_tag_filter,
    _estimate_included_tag_score,
    _wd_tag_exists_condition,
    apply_wd_model_filter,
)
from core.query.filters_tags_apply_or import apply_or_tags_filter


def apply_tag_filters(
    where_parts,
    params,
    tag_query,
    tag_query_regex,
    tag_query_case_sensitive,
    also_search_path=False,
    con=None,
    wd_model=None,
):
    if not (tag_query and tag_query.strip()):
        return
    if tag_query_regex:
        _apply_regex_tag_filter(where_parts, params, tag_query, tag_query_case_sensitive)
        return

    positives = []
    for tag in parse_tag_query(tag_query):
        if tag.startswith("-"):
            _apply_excluded_tag(where_parts, params, tag[1:], tag_query_case_sensitive, con)
            continue
        positives.append(tag)

    if len(positives) > 1:
        positives.sort(
            key=lambda tag: _estimate_included_tag_score(
                tag,
                tag_query_case_sensitive,
                also_search_path,
                con,
            )
        )

    positive_count = len(positives)
    for positive_index, tag in enumerate(positives):
        _apply_included_tag(
            where_parts,
            params,
            tag,
            tag_query_case_sensitive,
            also_search_path,
            con,
            positive_count=positive_count,
            positive_index=positive_index,
        )
        # Extend with WD-tagger tag match using active model (OR semantics per tag).
        # _apply_included_tag always appends exactly one condition; pop and re-wrap.
        wd = _wd_tag_exists_condition(tag, con, wd_model)
        if wd is not None and where_parts:
            wd_sql, wd_params = wd
            main_cond = where_parts.pop()
            where_parts.append(f"({main_cond} OR {wd_sql})")
            params.extend(wd_params)


__all__ = ["apply_or_tags_filter", "apply_tag_filters", "apply_wd_model_filter"]
