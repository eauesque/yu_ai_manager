"""Search and filter validators for MCP tools."""


from .validators_common import DEBUG_QUERY_LIMIT_MAX, SEARCH_LIMIT_MAX, VALID_FILE_FORMATS, VALID_SORTS, err


def validate_sort(sort: str) -> str | None:
    if sort and sort not in VALID_SORTS:
        return err(f"Invalid sort value: '{sort}'. Valid options: {', '.join(sorted(VALID_SORTS))}")
    return None


def validate_search_limit(limit: int) -> tuple[int, None]:
    return max(1, min(limit, SEARCH_LIMIT_MAX)), None


def validate_rating_range(min_rating: str, max_rating: str) -> str | None:
    vals = {}
    for label, raw in [("min_rating", min_rating), ("max_rating", max_rating)]:
        if not raw:
            continue
        try:
            value = int(raw)
        except (ValueError, TypeError):
            return err(f"Invalid {label}: '{raw}' (must be integer 0-5)")
        if value < 0 or value > 5:
            return err(f"{label} out of range: {value} (must be 0-5)")
        vals[label] = value
    if "min_rating" in vals and "max_rating" in vals and vals["min_rating"] > vals["max_rating"]:
        return err(f"min_rating ({vals['min_rating']}) > max_rating ({vals['max_rating']})")
    return None


def validate_file_format(file_format: str) -> str | None:
    if not file_format or file_format == "all":
        return None
    if file_format.lower() not in VALID_FILE_FORMATS:
        return err(f"Invalid file_format: '{file_format}'. Valid options: {', '.join(sorted(VALID_FILE_FORMATS))}")
    return None


def validate_confidence_range(min_confidence: str, max_confidence: str) -> str | None:
    vals = {}
    for label, raw in [("min_confidence", min_confidence), ("max_confidence", max_confidence)]:
        if not raw:
            continue
        try:
            value = float(raw)
        except (ValueError, TypeError):
            return err(f"Invalid {label}: '{raw}' (must be float 0.0-1.0)")
        if value < 0.0 or value > 1.0:
            return err(f"{label} out of range: {value} (must be 0.0-1.0)")
        vals[label] = value
    if "min_confidence" in vals and "max_confidence" in vals and vals["min_confidence"] > vals["max_confidence"]:
        return err(f"min_confidence ({vals['min_confidence']}) > max_confidence ({vals['max_confidence']})")
    return None


def validate_debug_limit(limit: int) -> str | None:
    if limit < 1 or limit > DEBUG_QUERY_LIMIT_MAX:
        return err(f"limit out of range: {limit} (must be 1-{DEBUG_QUERY_LIMIT_MAX})")
    return None


def validate_date_range(from_date: str, to_date: str) -> str | None:
    if from_date and to_date and from_date > to_date:
        return err(f"from_date ({from_date}) is after to_date ({to_date})")
    return None
