"""Route handler for similar image finding."""


from core.tools.similar_find import find_similar_to


def find_similar_payload(args) -> tuple[dict, int]:
    """Parse args and return similar-find results."""
    file_id_str = args.get("file_id", "")
    if not file_id_str:
        return {"error": "file_id required"}, 400
    try:
        file_id = int(file_id_str)
    except ValueError:
        return {"error": "invalid file_id"}, 400

    threshold = int(args.get("threshold", "5"))
    threshold = max(1, min(threshold, 20))

    result = find_similar_to(file_id, threshold)
    if "error" in result:
        return {"error": result["message"]}, 404
    results = result["results"]
    return {"file_id": file_id, "threshold": threshold, "results": results, "count": len(results)}, 200
