"""Annotation roundtrip validation."""

from .debug_helpers import _check, _g


def run_annotation_roundtrip(client, test_file_id: int):
    checks = []
    source = "debug:roundtrip"
    key = "__debug_test"
    created_at_1 = None

    try:
        write_resp = client.post("/api/annotations/batch-set", {"items": [{"file_id": test_file_id, "source": source, "key": key, "value": "v1", "confidence": 0.5}]})
        write_data = _g(write_resp, "data", write_resp)
        checks.append(_check("ann_write", "pass" if _g(write_data, "succeeded", 0) == 1 else "fail", file_id=test_file_id, response=write_data))
    except Exception as e:
        checks.append(_check("ann_write", "fail", file_id=test_file_id, error=str(e)))

    try:
        read_resp = client.get(f"/api/annotations/{test_file_id}", {"source": source, "key": key})
        anns = _g(_g(read_resp, "data", read_resp), "annotations", read_resp.get("annotations", []))
        found = [a for a in anns if a.get("key") == key]
        created_at_1 = found[0].get("created_at") if found else None
        checks.append(_check("ann_read", "pass" if len(found) == 1 and found[0].get("value") == "v1" else "fail", file_id=test_file_id, found=len(found)))
    except Exception as e:
        checks.append(_check("ann_read", "fail", file_id=test_file_id, error=str(e)))

    try:
        upsert_resp = client.post("/api/annotations/batch-set", {"items": [{"file_id": test_file_id, "source": source, "key": key, "value": "v2", "confidence": 0.9}]})
        checks.append(_check("ann_upsert", "pass" if _g(_g(upsert_resp, "data", upsert_resp), "succeeded", 0) == 1 else "fail", file_id=test_file_id))
    except Exception as e:
        checks.append(_check("ann_upsert", "fail", file_id=test_file_id, error=str(e)))

    try:
        verify_resp = client.get(f"/api/annotations/{test_file_id}", {"source": source, "key": key})
        anns = _g(_g(verify_resp, "data", verify_resp), "annotations", verify_resp.get("annotations", []))
        found = [a for a in anns if a.get("key") == key]
        if found and created_at_1:
            created_at_2 = found[0].get("created_at")
            ok = created_at_1 == created_at_2 and found[0].get("value") == "v2"
            checks.append(_check("bug06_created_at", "pass" if ok else "fail", file_id=test_file_id, before=created_at_1, after=created_at_2))
        else:
            checks.append(_check("bug06_created_at", "skip", file_id=test_file_id, detail="no created_at to compare"))
    except Exception as e:
        checks.append(_check("bug06_created_at", "fail", file_id=test_file_id, error=str(e)))

    try:
        delete_resp = client.post("/api/annotations/batch-delete", {"source": source, "file_ids": [test_file_id], "key": key})
        checks.append(_check("ann_delete", "pass" if delete_resp.get("ok") else "fail", file_id=test_file_id))
    except Exception as e:
        checks.append(_check("ann_delete", "fail", file_id=test_file_id, error=str(e)))
    return checks
