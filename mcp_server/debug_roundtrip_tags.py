"""Tag roundtrip validation."""

import contextlib

from .debug_helpers import _check, _g


def run_tag_roundtrip(client, test_file_id: int):
    checks = []
    tag_name = "__debug_tag"
    try:
        write_resp = client.post("/api/tags/batch-set", {"items": [{"file_id": test_file_id, "add": [tag_name], "remove": []}]})
        write_data = _g(write_resp, "data", write_resp)
        if _g(write_data, "succeeded", 0) != 1:
            checks.append(_check("tag_roundtrip", "fail", file_id=test_file_id, detail="batch-set failed", write_response=write_data, write_errors=_g(write_data, "errors", [])))
        else:
            detail = client.get(f"/api/file/{test_file_id}")
            tags = _g(_g(detail, "data", detail), "tags", detail.get("tags", []))
            tag_names = [t.get("tag", t) if isinstance(t, dict) else str(t) for t in tags]
            checks.append(_check("tag_roundtrip", "pass" if tag_name in tag_names else "fail", file_id=test_file_id, found=tag_name in tag_names, tag_count=len(tags)))
        client.post("/api/tags/batch-set", {"items": [{"file_id": test_file_id, "add": [], "remove": [tag_name]}]})
    except Exception as e:
        checks.append(_check("tag_roundtrip", "fail", file_id=test_file_id, error=str(e)))
        with contextlib.suppress(Exception):
            client.post("/api/tags/batch-set", {"items": [{"file_id": test_file_id, "add": [], "remove": [tag_name]}]})
    return checks
