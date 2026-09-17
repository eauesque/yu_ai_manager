"""Parse WD-Tagger selected_tags.csv from HuggingFace models.

The CSV contains tag names and their category indices:
  0 = general, 4 = character, 3 = copyright, 9 = rating
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# WD-Tagger category index to name mapping
CATEGORY_MAP: dict[int, str] = {
    0: "general",
    4: "character",
    3: "copyright",
    9: "rating",
}

# Default category for unmapped indices
DEFAULT_CATEGORY = "general"


def parse_tags_csv(csv_path: Path) -> tuple[list[str], list[str]]:
    """Parse selected_tags.csv and return (tag_names, categories).

    Returns two parallel lists: tag names and their category strings.
    The order matches the model output tensor indices.
    """
    tag_names: list[str] = []
    categories: list[str] = []

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("name", "").strip()
            if not name:
                continue
            cat_idx = int(row.get("category", "0"))
            category = CATEGORY_MAP.get(cat_idx, DEFAULT_CATEGORY)
            tag_names.append(name)
            categories.append(category)

    logger.info("Parsed %d tags from %s", len(tag_names), csv_path.name)
    return tag_names, categories


def get_rating_tags(tag_names: list[str], categories: list[str]) -> list[int]:
    """Return indices of rating-category tags."""
    return [i for i, cat in enumerate(categories) if cat == "rating"]


def get_general_indices(categories: list[str]) -> list[int]:
    """Return indices of general-category tags."""
    return [i for i, cat in enumerate(categories) if cat == "general"]


def get_character_indices(categories: list[str]) -> list[int]:
    """Return indices of character-category tags."""
    return [i for i, cat in enumerate(categories) if cat == "character"]


def get_copyright_indices(categories: list[str]) -> list[int]:
    """Return indices of copyright-category tags."""
    return [i for i, cat in enumerate(categories) if cat == "copyright"]
