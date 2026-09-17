"""Roundtrip test implementation for MCP debug tools."""

from .debug_helpers import _json, _summarize
from .debug_roundtrip_annotations import run_annotation_roundtrip
from .debug_roundtrip_ratings import run_rating_roundtrip
from .debug_roundtrip_tags import run_tag_roundtrip
from .debug_roundtrip_utils import cleanup_stale_roundtrip_data, resolve_roundtrip_file_id


def roundtrip_test(client) -> str:
    """Write -> read -> upsert -> verify -> cleanup roundtrip."""
    checks = []
    cleanup_stale_roundtrip_data(client)
    test_file_id = resolve_roundtrip_file_id(client)
    if test_file_id is None:
        return _json({"ok": False, "error": "no files in DB for roundtrip test"})
    checks.extend(run_annotation_roundtrip(client, test_file_id))
    checks.extend(run_rating_roundtrip(client, test_file_id))
    checks.extend(run_tag_roundtrip(client, test_file_id))
    return _json(_summarize(checks))
