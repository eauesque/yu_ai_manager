"""Tag filter facade (compatibility layer)."""

from core.query.filters_tags_apply import (
    apply_or_tags_filter,
    apply_tag_filters,
    apply_wd_model_filter,
)
from core.query.filters_tags_path import (
    path_search_condition as _path_search_condition,
)
from core.query.filters_tags_path import (
    path_search_params as _path_search_params,
)

__all__ = [
    "apply_or_tags_filter",
    "apply_tag_filters",
    "apply_wd_model_filter",
    "_path_like_conditions",
    "_path_like_params",
]


def _path_like_conditions(tag_val: str) -> str:
    return _path_search_condition(tag_val)


def _path_like_params(tag_val: str):
    return _path_search_params(tag_val)
