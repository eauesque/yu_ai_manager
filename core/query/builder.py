from typing import Any

from .filters import (
    apply_artist_filter,
    apply_checkpoint_filter,
    apply_date_filters,
    apply_file_format_filter,
    apply_model_filter,
    apply_or_tags_filter,
    apply_path_filter,
    apply_prompt_filters,
    apply_rating_filter,
    apply_resolution_filter,
    apply_tag_filters,
    apply_wd_model_filter,
)
from .filters_extension import apply_extension_filters
from .sort import build_sort_clause


def build_query_sql(
    tag_query: str | None,
    artist: str | None,
    from_date: str | None,
    to_date: str | None,
    in_prompt: str | None,
    file_format: str | None,
    format_exts: str | None,
    sort_by: str,
    limit: int,
    in_prompt_regex: bool = False,
    tag_query_regex: bool = False,
    tag_query_case_sensitive: bool = False,
    model_filter: str | None = None,
    checkpoint_filter: str | None = None,
    in_negative: str | None = None,
    in_char_negative: str | None = None,
    in_char_positive: str | None = None,
    from_ts: int | None = None,
    to_ts: int | None = None,
    offset: int = 0,
    in_path: str | None = None,
    min_width: int | None = None,
    max_width: int | None = None,
    min_height: int | None = None,
    max_height: int | None = None,
    or_tags: str | None = None,
    also_search_path: bool = True,
    fav_only: bool = False,
    collection_id: int = 0,
    min_rating: int | None = None,
    max_rating: int | None = None,
    ai_analyzed: bool = False,
    has_tags: bool = False,
    has_annotation: bool = False,
    has_sweep: bool = False,
    cursor_data: dict[str, Any] | None = None,
    cursor_direction: str | None = None,
    cursor_mtime: int | None = None,
    cursor_id: int | None = None,
    con=None,
    wd_model: str | None = None,
) -> tuple[str, list[Any], str, list[Any]]:
    where_parts = ["f.is_deleted=0"]
    params: list[Any] = []

    effective_also_path = also_search_path and not (in_path and in_path.strip())
    apply_date_filters(where_parts, params, from_date, to_date, from_ts, to_ts)
    apply_path_filter(where_parts, params, in_path, con=con)
    apply_tag_filters(where_parts, params, tag_query, tag_query_regex, tag_query_case_sensitive, also_search_path=effective_also_path, con=con, wd_model=wd_model)
    apply_artist_filter(where_parts, params, artist, con=con)
    apply_file_format_filter(where_parts, file_format, format_exts)
    apply_model_filter(where_parts, model_filter)
    apply_checkpoint_filter(where_parts, params, checkpoint_filter)
    apply_resolution_filter(where_parts, params, min_width, max_width, min_height, max_height)
    apply_or_tags_filter(where_parts, params, or_tags, con=con, wd_model=wd_model)
    apply_wd_model_filter(where_parts, params, wd_model, con=con)
    join_fts = apply_prompt_filters(where_parts, params, in_prompt, in_negative, in_char_negative, in_char_positive, con=con)
    need_rating_join = apply_rating_filter(where_parts, params, min_rating, max_rating)

    if ai_analyzed:
        from core.services_core import wd_active_model
        from core.services_core.wd_dict_resolver import resolve_model_id_readonly

        active_wd_model_id = (
            wd_active_model.try_get_active_wd_model_id_for_legacy_schema()
        )
        if active_wd_model_id is None:
            where_parts.append(
                "(EXISTS (SELECT 1 FROM analysis a WHERE a.file_id=f.id)"
                " OR EXISTS (SELECT 1 FROM file_wd_tags wt WHERE wt.file_id=f.id))"
            )
        else:
            if con is None:
                raise ValueError(
                    "build_query_sql requires con when ai_analyzed resolves an active WD model"
                )
            active_wd_model_db_id = resolve_model_id_readonly(
                con,
                active_wd_model_id,
            )
            if active_wd_model_db_id is None:
                where_parts.append(
                    "EXISTS (SELECT 1 FROM analysis a WHERE a.file_id=f.id)"
                )
            else:
                where_parts.append(
                    "(EXISTS (SELECT 1 FROM analysis a WHERE a.file_id=f.id)"
                    " OR EXISTS (SELECT 1 FROM file_wd_tags wt "
                    "WHERE wt.file_id=f.id AND wt.model_id=?))"
                )
                params.append(active_wd_model_db_id)

    if has_tags:
        where_parts.append(
            "EXISTS (SELECT 1 FROM file_tags ft2 WHERE ft2.file_id=f.id)"
        )

    if has_annotation:
        where_parts.append(
            "EXISTS (SELECT 1 FROM file_annotations fa WHERE fa.file_id=f.id)"
        )

    if has_sweep:
        where_parts.append("f.has_sweep=1")

    # Extension hook: on_search_filter
    apply_extension_filters(where_parts, params)

    join_fav = ""
    if collection_id > 0:
        join_fav = "JOIN favorites fav ON fav.file_id=f.id AND fav.collection_id=? "
        params.insert(0, collection_id)
    elif collection_id == -1 or fav_only:
        # -1 means "all favorites across all collections"
        join_fav = "JOIN favorites fav ON fav.file_id=f.id "

    join_rating = "JOIN file_ratings rt ON rt.file_id=f.id " if need_rating_join else ""

    count_where = list(where_parts)
    count_params = list(params)

    if cursor_data is None and cursor_direction and cursor_mtime is not None and cursor_id is not None:
        cursor_data = {"type": "date", "direction": cursor_direction,
                       "mtime": cursor_mtime, "id": cursor_id}

    extra_select = ""
    if cursor_data is not None:
        ks_type = cursor_data.get("type")
        ks_dir = cursor_data.get("direction", "desc")

        if ks_type == "date":
            _mtime = cursor_data["mtime"]
            _fid = cursor_data["id"]
            if ks_dir == "desc":
                where_parts.append("(f.mtime < ? OR (f.mtime = ? AND f.id < ?))")
                sort_clause = "ORDER BY f.mtime DESC, f.id DESC"
            else:
                where_parts.append("(f.mtime > ? OR (f.mtime = ? AND f.id > ?))")
                sort_clause = "ORDER BY f.mtime ASC, f.id ASC"
            params.extend([_mtime, _mtime, _fid])
            sort_params: list[Any] = []
            sort_join = ""
            offset = 0

        elif ks_type == "rating":
            _rating = cursor_data.get("rating")
            _mtime = cursor_data["mtime"]
            _fid = cursor_data["id"]
            sort_join = "LEFT JOIN file_ratings rt_sort ON rt_sort.file_id=f.id "
            extra_select = ", rt_sort.rating AS _sort_rating"

            if ks_dir == "desc":
                if _rating is not None:
                    where_parts.append(
                        "(rt_sort.rating IS NULL "
                        "OR rt_sort.rating < ? "
                        "OR (rt_sort.rating = ? AND f.mtime < ?) "
                        "OR (rt_sort.rating = ? AND f.mtime = ? AND f.id < ?))"
                    )
                    params.extend([_rating, _rating, _mtime, _rating, _mtime, _fid])
                else:
                    where_parts.append(
                        "(rt_sort.rating IS NULL "
                        "AND (f.mtime < ? OR (f.mtime = ? AND f.id < ?)))"
                    )
                    params.extend([_mtime, _mtime, _fid])
                sort_clause = (
                    "ORDER BY rt_sort.rating IS NULL, rt_sort.rating DESC, "
                    "f.mtime DESC, f.id DESC"
                )
            else:
                if _rating is not None:
                    where_parts.append(
                        "(rt_sort.rating IS NULL "
                        "OR rt_sort.rating > ? "
                        "OR (rt_sort.rating = ? AND f.mtime < ?) "
                        "OR (rt_sort.rating = ? AND f.mtime = ? AND f.id < ?))"
                    )
                    params.extend([_rating, _rating, _mtime, _rating, _mtime, _fid])
                else:
                    where_parts.append(
                        "(rt_sort.rating IS NULL "
                        "AND (f.mtime < ? OR (f.mtime = ? AND f.id < ?)))"
                    )
                    params.extend([_mtime, _mtime, _fid])
                sort_clause = (
                    "ORDER BY rt_sort.rating IS NULL, rt_sort.rating ASC, "
                    "f.mtime DESC, f.id DESC"
                )
            sort_params = []
            offset = 0

        elif ks_type == "path":
            _path = cursor_data["path"]
            _fid = cursor_data["id"]
            where_parts.append("(f.path > ? OR (f.path = ? AND f.id > ?))")
            params.extend([_path, _path, _fid])
            sort_clause = "ORDER BY f.path ASC, f.id ASC"
            sort_params = []
            sort_join = ""
            offset = 0

        else:
            sort_clause, sort_params, sort_join = build_sort_clause(sort_by)
    else:
        sort_clause, sort_params, sort_join = build_sort_clause(sort_by)

    where_text = " AND ".join(where_parts)
    count_where_text = " AND ".join(count_where)
    need_templates_in_where = "tm." in where_text or "tf." in where_text
    need_templates_in_count = "tm." in count_where_text or "tf." in count_where_text

    if join_fts:
        templates_join = "JOIN templates tm ON tm.file_id=f.id "
    else:
        templates_join = "LEFT JOIN templates tm ON tm.file_id=f.id "

    include_templates = need_templates_in_where or bool(join_fts)

    from_clause = (
        "FROM files f "
        + (templates_join if include_templates else "")
        + join_fav
        + join_rating
        + (join_fts + " " if join_fts else "")
        + sort_join
    )

    if include_templates:
        select_cols = "SELECT f.id, f.path, f.mtime, f.meta_source, tm.raw_prompt, tm.raw_negative"
    else:
        select_cols = "SELECT f.id, f.path, f.mtime, f.meta_source, NULL AS raw_prompt, NULL AS raw_negative"

    sql = (
        select_cols
        + extra_select
        + " "
        + from_clause
        + "WHERE "
        + where_text
        + " "
        + sort_clause
        + " "
        + "LIMIT ? OFFSET ?"
    )
    params.extend(sort_params)
    params.append(limit)
    params.append(offset)

    count_from = (
        "FROM files f "
        + (templates_join if need_templates_in_count else "")
        + join_fav
        + join_rating
        + (join_fts + " " if need_templates_in_count else "")
    )
    count_sql = (
        "SELECT COUNT(*) " + count_from
        + "WHERE " + count_where_text
    )

    return sql, params, count_sql, count_params
