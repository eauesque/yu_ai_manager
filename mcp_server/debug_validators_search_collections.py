"""Collection validator implementation."""


from .client import YuManagerClient
from .debug_helpers import _check, _g, _json, _sql, _summarize


def validate_collection(client: YuManagerClient) -> str:
    checks: list[dict] = []
    colls = client.get("/api/collections")
    coll_list = _g(_g(colls, "data", colls), "collections", colls.get("collections", []))

    for coll in coll_list[:10]:
        cid = coll.get("id")
        cached = coll.get("file_count", coll.get("count", 0))
        res = _sql(client, f"SELECT COUNT(*) as cnt FROM favorites WHERE collection_id={int(cid)}")
        if res.get("rows"):
            actual = res["rows"][0]["cnt"]
            checks.append(_check(f"collection_{cid}_count", "pass" if cached == actual else "fail", cached=cached, actual=actual, coll_name=coll.get("name", "")))

    res = _sql(client, "SELECT COUNT(*) as cnt FROM favorites fv LEFT JOIN files f ON fv.file_id=f.id WHERE f.id IS NULL")
    if res.get("rows"):
        cnt = res["rows"][0]["cnt"]
        checks.append(_check("orphan_favorites", "pass" if cnt == 0 else "warn", count=cnt))

    if not checks:
        checks.append(_check("no_collections", "skip"))
    return _json(_summarize(checks))
