"""Predicate helpers for count-only search fast paths."""

from __future__ import annotations

from core.prompt import parse_tag_query

COUNT_IMAGE_EXTS = (
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp",
    ".tif", ".tiff", ".avif", ".heif", ".heic", ".jxl", ".svg",
)


def has_non_tag_count_filters(p: dict) -> bool:
    return any(
        [
            p.get("artist"),
            p.get("from_date"),
            p.get("to_date"),
            p.get("from_ts_int"),
            p.get("to_ts_int"),
            p.get("in_prompt"),
            p.get("in_prompt_regex"),
            p.get("in_negative"),
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


def can_use_negative_tag_count_fast_path(p: dict) -> bool:
    if p.get("tag_query_regex"):
        return False
    tags = parse_tag_query(p.get("tag_query") or "")
    if not tags or any(not tag.startswith("-") for tag in tags):
        return False
    return not has_non_tag_count_filters(p)


def can_use_single_positive_tag_count_fast_path(p: dict) -> bool:
    if p.get("tag_query_regex") or has_non_tag_count_filters(p):
        return False
    tags = parse_tag_query(p.get("tag_query") or "")
    return len(tags) == 1 and not tags[0].startswith("-")


def _has_common_non_tag_candidate_filters(p: dict) -> bool:
    return any(
        [
            p.get("artist"),
            p.get("from_date"),
            p.get("to_date"),
            p.get("from_ts_int"),
            p.get("to_ts_int"),
            p.get("in_prompt"),
            p.get("in_prompt_regex"),
            p.get("in_negative"),
            p.get("in_char_negative"),
            p.get("in_char_positive"),
            p.get("checkpoint_filter"),
            p.get("in_path"),
            p.get("or_tags"),
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


def can_use_tag_candidate_count_fast_path(p: dict) -> bool:
    if p.get("tag_query_regex"):
        return False
    tags = parse_tag_query(p.get("tag_query") or "")
    positive_count = sum(1 for tag in tags if not tag.startswith("-"))
    return positive_count == 1 and not _has_common_non_tag_candidate_filters(p)


def can_fast_count_file_format(file_format: str | None) -> bool:
    ff = "all" if not file_format or file_format == "all" else file_format.lower()
    return ff in {
        "all", "image", "mp4", "gif", "jpg", "jpeg",
        "avif", "jxl", "heif", "heic", "svg",
    }


def _has_common_non_plain_filters(p: dict, *, allow_key: str | None = None) -> bool:
    keys = [
        "tag_query", "tag_query_regex", "artist", "from_date", "to_date",
        "from_ts_int", "to_ts_int", "in_prompt", "in_prompt_regex",
        "in_negative", "in_char_negative", "in_char_positive",
        "checkpoint_filter", "in_path", "or_tags", "format_exts",
        "ai_analyzed", "has_tags", "has_annotation", "has_sweep",
    ]
    if any(key != allow_key and p.get(key) for key in keys):
        return True
    return any(
        [
            p.get("file_format") != "all",
            p.get("model_filter") != "all",
            p.get("fav_only", False),
            p.get("collection_id", 0) != 0,
            p.get("min_rating") is not None,
            p.get("max_rating") is not None,
            p.get("min_width_int") is not None,
            p.get("max_width_int") is not None,
            p.get("min_height_int") is not None,
            p.get("max_height_int") is not None,
        ]
    )


def can_use_ai_analyzed_count_fast_path(p: dict) -> bool:
    return bool(p.get("ai_analyzed", False)) and not _has_common_non_plain_filters(p, allow_key="ai_analyzed")


def can_use_path_only_count_fast_path(p: dict) -> bool:
    return bool((p.get("in_path") or "").strip()) and not _has_common_non_plain_filters(p, allow_key="in_path")


def can_use_has_tags_count_fast_path(p: dict) -> bool:
    return bool(p.get("has_tags", False)) and not _has_common_non_plain_filters(p, allow_key="has_tags")


def can_use_plain_count_fast_path(p: dict) -> bool:
    return not _has_common_non_plain_filters(p)


def count_file_format_clause(file_format: str | None) -> str | None:
    ff = "all" if not file_format or file_format == "all" else file_format.lower()
    if ff == "all":
        return ""
    ext_groups = {
        "image": COUNT_IMAGE_EXTS,
        "jpg": (".jpg", ".jpeg"),
        "jpeg": (".jpg", ".jpeg"),
        "heif": (".heif", ".heic"),
        "heic": (".heif", ".heic"),
    }
    if ff in ext_groups:
        quoted = ",".join(f"'{ext}'" for ext in ext_groups[ff])
        return f"f.file_ext IN ({quoted})"
    if ff in {"mp4", "gif", "avif", "jxl", "svg"}:
        return f"f.file_ext = '.{ff}'"
    return None
