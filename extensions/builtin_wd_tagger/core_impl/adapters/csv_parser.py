"""Column-mapping driven CSV parser for tagger profiles.

Each profile's tag_csv_spec specifies the column names and category mapping,
allowing different tagger families to share parsing logic.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def parse_tags_csv_with_spec(
    csv_path: Path,
    spec: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Parse a tags CSV using a tag_csv_spec."""
    delimiter = spec.get("delimiter", ",")
    name_col = spec["name_col"]
    cat_col = spec["category_col"]
    cat_map: dict[str, str] = dict(spec.get("category_map", {}))

    names: list[str] = []
    categories: list[str] = []

    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        for row in reader:
            raw_name = row.get(name_col, "")
            raw_cat = row.get(cat_col, "")
            names.append(raw_name)
            categories.append(cat_map.get(str(raw_cat), str(raw_cat)))

    return names, categories
