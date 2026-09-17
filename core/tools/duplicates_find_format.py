"""Formatting/filter helpers for duplicate finding."""

from pathlib import Path
from typing import Any


def filter_cross_directory(rows, method: str, cross_directory: bool):
    if not cross_directory or method == "phash":
        return rows

    filtered_rows = []
    for row in rows:
        paths = row[2].split("|||")
        dirs = set(str(Path(p).parent) for p in paths)
        if len(dirs) > 1:
            filtered_rows.append(row)
    return filtered_rows


def build_groups(rows, method: str) -> tuple[list[dict[str, Any]], int]:
    groups: list[dict[str, Any]] = []
    total_duplicates = 0

    for row in rows:
        if method == "phash":
            groups.append(row)
            total_duplicates += row["count"] - 1
            continue

        path_list = row[2].split("|||")
        id_list = row[3].split("|||") if row[3] else []
        groups.append({"hash": row[0], "count": row[1], "files": path_list, "ids": [int(i) for i in id_list if i]})
        total_duplicates += row[1] - 1

    return groups, total_duplicates
