"""Shared validation constants and helpers for MCP tools."""

import json

VALID_SORTS = {"date", "date_old", "date_new", "folder", "path", "random", "rating_desc", "rating_asc"}
VALID_FILE_FORMATS = {"all", "png", "webp", "jpg", "jpeg", "gif", "image", "video", "audio", "webm", "mp4", "zip_member", "avif", "jxl", "heif", "heic"}
BATCH_MAX = 500
SEARCH_LIMIT_MAX = 200
DEBUG_QUERY_LIMIT_MAX = 2000
ANNOTATION_SOURCE_KEY_MAX = 255
ANNOTATION_VALUE_MAX = 65536
VALID_PROMPT_SORTS = {"updated_at", "created_at", "title"}
PROMPT_TITLE_MAX = 200
VALID_HASH_TYPES = {"md5", "phash", "both"}
VALID_DUPLICATE_METHODS = {"hash", "phash", "size"}


def err(message: str) -> str:
    """Return a JSON error string."""
    return json.dumps({"ok": False, "error": message}, ensure_ascii=False)
