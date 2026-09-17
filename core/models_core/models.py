"""Compatibility facade for DB CRUD model helpers.

External compatibility only. Repo-internal code should prefer
``models_files``, ``models_tags``, and ``models_templates`` directly.
"""

from .models_files import get_file_row, get_file_rows_batch, mark_deleted, upsert_file
from .models_tags import (
    clear_tags_for_file,
    clear_tags_for_files_batch,
    insert_file_tag,
    insert_file_tags_batch,
    reset_tag_cache,
    upsert_tag,
)
from .models_templates import replace_template_tokens, upsert_template

__all__ = [
    "get_file_row",
    "get_file_rows_batch",
    "upsert_file",
    "clear_tags_for_file",
    "clear_tags_for_files_batch",
    "upsert_tag",
    "insert_file_tag",
    "insert_file_tags_batch",
    "reset_tag_cache",
    "mark_deleted",
    "upsert_template",
    "replace_template_tokens",
]
