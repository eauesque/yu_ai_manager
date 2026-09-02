"""Rating roundtrip validation."""

import contextlib

from .debug_helpers import _check, _g


def run_rating_roundtrip(client, test_file_id: int):
    checks = []
    try:
        write_resp = client.post("/api/ratings/batch-set", {"items": [{"file_id": test_file_id, "rating": 4}]})
        write_data = _g(write_resp, "data", write_resp)
        if _g(write_data, "succeeded", 0) != 1:
            checks.append(_check("rating_roundtrip", "fail", file_id=test_file_id, detail="batch-set failed", write_response=write_data, write_errors=_g(write_data, "errors", [])))
        else:
            verify_resp = client.get("/api/ratings/get", {"file_id": str(test_file_id)})
            db_rating = _g(verify_resp, "rating", None)
            checks.append(_check("rating_roundtrip", "pass" if db_rating == 4 else "fail", file_id=test_file_id, found=db_rating == 4, db_rating=db_rating))
        client.post("/api/ratings/batch-set", {"items": [{"file_id": test_file_id, "rating": 0}]})
    except Exception as e:
        checks.append(_check("rating_roundtrip", "fail", file_id=test_file_id, error=str(e)))
        with contextlib.suppress(Exception):
            client.post("/api/ratings/batch-set", {"items": [{"file_id": test_file_id, "rating": 0}]})
    return checks
