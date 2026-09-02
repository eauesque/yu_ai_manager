from typing import Any


def build_sort_clause(sort_by: str) -> tuple[str, list[Any], str]:
    """Return (sort_clause, params, extra_join) with parameterized values.

    extra_join: Additional JOIN clause needed for rating sort etc. Empty string if not needed.
    """
    params: list[Any] = []
    sort_clause = "ORDER BY f.mtime DESC, f.id DESC"
    extra_join = ""
    if sort_by in ("date_new", "date"):
        sort_clause = "ORDER BY f.mtime DESC, f.id DESC"
    elif sort_by == "date_old":
        sort_clause = "ORDER BY f.mtime ASC, f.id ASC"
    elif sort_by == "folder":
        import tagdb_tool

        _config = tagdb_tool.load_config_json(None)
        _roots = _config.get("scan_roots", [])
        if _roots:
            case_parts = []
            for i, root in enumerate(_roots):
                rp = root.get("path", "").replace("\\", "/")
                # i is only an integer from enumerate (not external input)
                idx = int(i)
                case_parts.append(
                    f"WHEN REPLACE(f.path, '\\\\', '/') LIKE ? THEN {idx}"
                )
                params.append(rp + "%")
            sort_clause = "ORDER BY " + ("CASE " + " ".join(case_parts) + " ELSE 9999 END") + ", f.path"
        else:
            sort_clause = "ORDER BY f.path"
    elif sort_by == "path":
        sort_clause = "ORDER BY f.path"
    elif sort_by == "random":
        sort_clause = "ORDER BY RANDOM()"
    elif sort_by == "rating_desc":
        extra_join = "LEFT JOIN file_ratings rt_sort ON rt_sort.file_id=f.id "
        sort_clause = (
            "ORDER BY rt_sort.rating IS NULL, rt_sort.rating DESC, f.mtime DESC"
        )
    elif sort_by == "rating_asc":
        extra_join = "LEFT JOIN file_ratings rt_sort ON rt_sort.file_id=f.id "
        sort_clause = (
            "ORDER BY rt_sort.rating IS NULL, rt_sort.rating ASC, f.mtime DESC"
        )
    return sort_clause, params, extra_join
