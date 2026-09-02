"""FTS-first execution strategy selectors and SQL builders for search."""

from core.query.filters_tags_apply import apply_tag_filters


def _templates_fts_has_char_columns(con) -> bool:
    if con is None:
        return False
    try:
        cols = [row[1] for row in con.execute("PRAGMA table_info(templates_fts)").fetchall()]
        return "char_positive" in cols and "char_negative" in cols
    except Exception:
        return False


def _can_use_prompt_fts_first_path(p: dict, keyset_info) -> bool:
    file_format = (p.get("file_format") or "")
    model_filter = (p.get("model_filter") or "")
    checkpoint_filter = (p.get("checkpoint_filter") or "")
    return (
        (
            bool((p.get("in_prompt") or "").strip())
            or bool((p.get("in_negative") or "").strip())
        )
        and not (
            bool((p.get("in_prompt") or "").strip())
            and bool((p.get("in_negative") or "").strip())
        )
        and not (p.get("in_char_negative") or "").strip()
        and not (p.get("in_char_positive") or "").strip()
        and not (p.get("artist") or "").strip()
        and file_format in ("", "all")
        and not (p.get("format_exts") or "").strip()
        and model_filter in ("", "all")
        and checkpoint_filter in ("", "all")
        and not (p.get("or_tags") or "").strip()
        and not (p.get("wd_model") or "").strip()
        and not (p.get("in_path") or "").strip()
        and not p.get("fav_only", False)
        and int(p.get("collection_id", 0) or 0) == 0
        and p.get("min_rating") is None
        and p.get("max_rating") is None
        and not p.get("ai_analyzed", False)
        and not p.get("has_tags", False)
        and not p.get("has_annotation", False)
        and not p.get("has_sweep", False)
        and not p.get("from_date")
        and not p.get("to_date")
        and p.get("from_ts_int") is None
        and p.get("to_ts_int") is None
        and keyset_info is None
        and p.get("sort_by") in ("date", "date_new")
    )


def _can_use_char_fts_first_path(p: dict, keyset_info, con) -> bool:
    file_format = (p.get("file_format") or "")
    model_filter = (p.get("model_filter") or "")
    checkpoint_filter = (p.get("checkpoint_filter") or "")
    return (
        _templates_fts_has_char_columns(con)
        and (
            bool((p.get("in_char_positive") or "").strip())
            or bool((p.get("in_char_negative") or "").strip())
        )
        and not (
            bool((p.get("in_char_positive") or "").strip())
            and bool((p.get("in_char_negative") or "").strip())
        )
        and not (p.get("in_prompt") or "").strip()
        and not (p.get("in_negative") or "").strip()
        and not (p.get("artist") or "").strip()
        and file_format in ("", "all")
        and not (p.get("format_exts") or "").strip()
        and model_filter in ("", "all")
        and checkpoint_filter in ("", "all")
        and not (p.get("or_tags") or "").strip()
        and not (p.get("wd_model") or "").strip()
        and not (p.get("in_path") or "").strip()
        and not p.get("fav_only", False)
        and int(p.get("collection_id", 0) or 0) == 0
        and p.get("min_rating") is None
        and p.get("max_rating") is None
        and not p.get("ai_analyzed", False)
        and not p.get("has_tags", False)
        and not p.get("has_annotation", False)
        and not p.get("has_sweep", False)
        and not p.get("from_date")
        and not p.get("to_date")
        and p.get("from_ts_int") is None
        and p.get("to_ts_int") is None
        and keyset_info is None
        and p.get("sort_by") in ("date", "date_new")
    )


def _build_prompt_fts_first_sql(p: dict, con):
    prompt_term = (p.get("in_prompt") or "").strip()
    negative_term = (p.get("in_negative") or "").strip()
    where_parts = ["f.is_deleted=0"]
    params = []
    if prompt_term:
        where_parts.append("tf.raw_prompt MATCH ?")
        params.append('"' + prompt_term.replace('"', '""') + '"')
    else:
        where_parts.append("tf.raw_negative MATCH ?")
        params.append('"' + negative_term.replace('"', '""') + '"')
    apply_tag_filters(
        where_parts,
        params,
        p.get("tag_query"),
        p.get("tag_query_regex", False),
        p.get("tag_query_case_sensitive", False),
        also_search_path=bool(p.get("also_path", True)),
        con=con,
        wd_model=p.get("wd_model"),
    )
    where_text = " AND ".join(where_parts)
    sql = (
        "SELECT f.id, f.path, f.mtime, f.meta_source, tm.raw_prompt, tm.raw_negative "
        "FROM templates_fts tf "
        "JOIN templates tm ON tm.id=tf.rowid "
        "JOIN files f ON f.id=tm.file_id "
        "WHERE "
        + where_text
        + " ORDER BY f.mtime DESC, f.id DESC LIMIT ? OFFSET ?"
    )
    count_sql = (
        "SELECT COUNT(*) "
        "FROM templates_fts tf "
        "JOIN templates tm ON tm.id=tf.rowid "
        "JOIN files f ON f.id=tm.file_id "
        "WHERE "
        + where_text
    )
    sql_params = list(params) + [p["limit"], p["offset"]]
    return sql, sql_params, count_sql, params


def _build_char_fts_first_sql(p: dict, con):
    positive_term = (p.get("in_char_positive") or "").strip()
    negative_term = (p.get("in_char_negative") or "").strip()
    where_parts = ["f.is_deleted=0"]
    params = []
    if positive_term:
        where_parts.append("tf.char_positive MATCH ?")
        params.append('"' + positive_term.replace('"', '""') + '"')
    else:
        where_parts.append("tf.char_negative MATCH ?")
        params.append('"' + negative_term.replace('"', '""') + '"')
    apply_tag_filters(
        where_parts,
        params,
        p.get("tag_query"),
        p.get("tag_query_regex", False),
        p.get("tag_query_case_sensitive", False),
        also_search_path=bool(p.get("also_path", True)),
        con=con,
        wd_model=p.get("wd_model"),
    )
    where_text = " AND ".join(where_parts)
    sql = (
        "SELECT f.id, f.path, f.mtime, f.meta_source, tm.raw_prompt, tm.raw_negative "
        "FROM templates_fts tf "
        "JOIN templates tm ON tm.id=tf.rowid "
        "JOIN files f ON f.id=tm.file_id "
        "WHERE "
        + where_text
        + " ORDER BY f.mtime DESC, f.id DESC LIMIT ? OFFSET ?"
    )
    count_sql = (
        "SELECT COUNT(*) "
        "FROM templates_fts tf "
        "JOIN templates tm ON tm.id=tf.rowid "
        "JOIN files f ON f.id=tm.file_id "
        "WHERE "
        + where_text
    )
    sql_params = list(params) + [p["limit"], p["offset"]]
    return sql, sql_params, count_sql, params
