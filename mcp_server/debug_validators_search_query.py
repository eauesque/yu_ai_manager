"""Search validator implementation."""


from .client import YuManagerClient
from .debug_helpers import _check, _g, _json, _summarize


def validate_search(client: YuManagerClient) -> str:
    checks: list[dict] = []

    r1 = client.get("/api/search", {"sort": "date", "limit": "2"})
    files1 = _g(_g(r1, "data", r1), "files", r1.get("files", []))
    if len(files1) >= 2:
        ok = files1[0].get("mtime", 0) >= files1[1].get("mtime", 0)
        checks.append(_check("sort_date_desc", "pass" if ok else "fail", first_mtime=files1[0].get("mtime"), second_mtime=files1[1].get("mtime")))
    else:
        checks.append(_check("sort_date_desc", "skip", detail="<2 files"))

    r = client.get("/api/search", {"model_filter": "sd", "limit": "5"})
    files = _g(_g(r, "data", r), "files", r.get("files", []))
    bad = [f["path"] for f in files if not (f.get("meta_source", "").startswith("a1111") or f.get("meta_source", "").startswith("forge"))]
    checks.append(_check("model_filter_sd", "pass" if not bad else "fail", bad_paths=bad[:3]))

    r_page1 = client.get("/api/search", {"sort": "date", "limit": "3"})
    cursor = _g(_g(r_page1, "data", r_page1), "next_cursor", r_page1.get("next_cursor", ""))
    if cursor:
        r_page2 = client.get("/api/search", {"sort": "date", "limit": "3", "cursor": cursor})
        p1_ids = {f["id"] for f in _g(_g(r_page1, "data", r_page1), "files", r_page1.get("files", []))}
        p2_ids = {f["id"] for f in _g(_g(r_page2, "data", r_page2), "files", r_page2.get("files", []))}
        checks.append(_check("cursor_continuity", "pass" if not (p1_ids & p2_ids) else "fail", overlap=list(p1_ids & p2_ids)))
    else:
        checks.append(_check("cursor_continuity", "skip", detail="no next_cursor"))

    for name, params in [
        ("bug01_invalid_collection", {"collection_id": "999999"}),
        ("bug02_invalid_date", {"from": "2026-02-30"}),
    ]:
        response = client.get("/api/search", params)
        checks.append(_check(name, "pass" if response.get("ok") is False or response.get("error") else "fail", response_ok=response.get("ok")))

    r_rand = client.get("/api/search", {"sort": "random", "limit": "3"})
    data_rand = _g(r_rand, "data", r_rand)
    cursor_rand = _g(data_rand, "next_cursor", r_rand.get("next_cursor"))
    checks.append(_check("bug20_random_no_cursor", "pass" if cursor_rand is None else "fail", next_cursor=cursor_rand))

    r = client.get("/api/search", {"sort": "rating_desc", "limit": "50"})
    files_rd = _g(_g(r, "data", r), "files", r.get("files", []))
    saw_null = False
    bug04_ok = True
    for file in files_rd:
        rating = file.get("rating")
        if rating is None or rating == 0:
            saw_null = True
        elif saw_null:
            bug04_ok = False
            break
    checks.append(_check("bug04_rating_null_last", "pass" if bug04_ok else "fail"))
    return _json(_summarize(checks))
