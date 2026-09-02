"""Search API request argument parsing."""

from core.infra_core.api_params import get_bool_arg, get_int_arg, get_str_arg
from core.search_api.utils import SQLITE_MAX_INT, as_int_or_none, safe_int


def parse_search_args(args):
    tag_query = get_str_arg(args, ("q", "query", "tag", "tags"), "")
    artist = get_str_arg(args, ("artist", "a"), "")
    from_date = get_str_arg(args, ("from", "start", "start_date"), "")
    to_date = get_str_arg(args, ("to", "end", "end_date"), "")
    from_ts = get_str_arg(args, ("from_ts", "start_ts"), "")
    to_ts = get_str_arg(args, ("to_ts", "end_ts"), "")
    in_prompt = get_str_arg(args, ("in_prompt", "prompt"), "")
    in_negative = get_str_arg(args, ("in_negative", "negative"), "")
    in_char_negative = get_str_arg(args, ("in_char_negative", "char_negative"), "")
    in_char_positive = get_str_arg(args, ("in_char_positive", "char_positive"), "")
    file_format = get_str_arg(args, ("format", "file_format", "type"), "all")
    format_exts = get_str_arg(args, ("format_exts", "exts", "extensions"), "")
    sort_by = get_str_arg(args, ("sort", "sort_by", "order"), "date")
    limit = get_int_arg(args, ("limit", "n", "page_size"), 100, minimum=1, maximum=2000)
    offset = get_int_arg(args, ("offset", "skip"), 0, minimum=0, maximum=SQLITE_MAX_INT)
    cursor = get_str_arg(args, ("cursor", "after"), "")
    in_prompt_regex = get_bool_arg(args, ("in_prompt_regex", "prompt_regex", "regex_prompt"), False)
    tag_query_regex = get_bool_arg(args, ("tag_regex", "q_regex", "regex"), False)
    tag_query_case_sensitive = get_bool_arg(args, ("tag_case", "case_sensitive"), False)
    if tag_query_regex or in_prompt_regex:
        limit = min(limit, 1000)

    model_filter = get_str_arg(args, ("model_filter", "model_type"), "all")
    checkpoint_filter = get_str_arg(args, ("checkpoint", "ckpt"), "")
    in_path = get_str_arg(args, ("in_path", "path"), "")
    or_tags = get_str_arg(args, ("or_tags", "tags_or"), "")
    wd_model = get_str_arg(args, ("wd_model", "wd_tagger_model"), "")
    also_path = get_bool_arg(args, ("also_path", "search_path"), True)
    fav_only = get_bool_arg(args, ("fav_only", "favorites"), False)
    ai_analyzed = get_bool_arg(args, ("ai_analyzed",), False)
    has_tags = get_bool_arg(args, ("has_tags", "tagged"), False)
    has_annotation = get_bool_arg(args, ("has_annotation",), False)
    has_sweep = get_bool_arg(args, ("has_sweep", "sweep_only"), False)
    collection_id = get_int_arg(args, ("collection_id", "coll"), 0, minimum=-1, maximum=SQLITE_MAX_INT)
    min_rating = as_int_or_none(get_str_arg(args, ("min_rating", "rating_min"), ""))
    max_rating = as_int_or_none(get_str_arg(args, ("max_rating", "rating_max"), ""))
    min_width_int = as_int_or_none(get_str_arg(args, ("min_width", "w_min"), ""))
    max_width_int = as_int_or_none(get_str_arg(args, ("max_width", "w_max"), ""))
    min_height_int = as_int_or_none(get_str_arg(args, ("min_height", "h_min"), ""))
    max_height_int = as_int_or_none(get_str_arg(args, ("max_height", "h_max"), ""))
    from_ts_int = safe_int(from_ts)
    to_ts_int = safe_int(to_ts)

    return {
        "tag_query": tag_query,
        "artist": artist,
        "from_date": from_date,
        "to_date": to_date,
        "in_prompt": in_prompt,
        "in_negative": in_negative,
        "in_char_negative": in_char_negative,
        "in_char_positive": in_char_positive,
        "file_format": file_format,
        "format_exts": format_exts,
        "sort_by": sort_by,
        "limit": limit,
        "offset": offset,
        "cursor": cursor,
        "in_prompt_regex": in_prompt_regex,
        "tag_query_regex": tag_query_regex,
        "tag_query_case_sensitive": tag_query_case_sensitive,
        "model_filter": model_filter,
        "checkpoint_filter": checkpoint_filter,
        "in_path": in_path,
        "or_tags": or_tags,
        "wd_model": wd_model,
        "min_width_int": min_width_int,
        "max_width_int": max_width_int,
        "min_height_int": min_height_int,
        "max_height_int": max_height_int,
        "from_ts_int": from_ts_int,
        "to_ts_int": to_ts_int,
        "also_path": also_path,
        "fav_only": fav_only,
        "ai_analyzed": ai_analyzed,
        "has_tags": has_tags,
        "has_annotation": has_annotation,
        "has_sweep": has_sweep,
        "collection_id": collection_id,
        "min_rating": min_rating,
        "max_rating": max_rating,
    }


def has_search_conditions(params: dict) -> bool:
    return any(
        [
            params["tag_query"],
            params["artist"],
            params["from_date"],
            params["to_date"],
            params["in_prompt"],
            params["in_negative"],
            params["in_char_negative"],
            params["checkpoint_filter"],
            params["in_char_positive"],
            params["from_ts_int"],
            params["to_ts_int"],
            params["file_format"] != "all",
            params["format_exts"],
            params["model_filter"] != "all",
            params.get("fav_only", False),
            params.get("collection_id", 0) != 0,
            params.get("in_path", ""),
            params.get("ai_analyzed", False),
            params.get("has_tags", False),
            params.get("has_annotation", False),
            params.get("has_sweep", False),
            params.get("min_rating") is not None,
            params.get("max_rating") is not None,
            params.get("wd_model"),
        ]
    )
