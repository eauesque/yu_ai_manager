"""MODELS.rst parsing helpers for Hailo GenAI registry."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedModel:
    section: str
    hef_filename: str
    url: str


HEF_URL_RE = re.compile(r"https?://[^\s)>\"']+?\.hef[^\s)>\"']*")
SECTION_UNDERLINE_CHARS = set("=-~")
SKIP_SECTION_KEYWORDS = ("image encoders only", "vision encoders only")


def should_skip_section(name: str) -> bool:
    lowered = name.lower()
    return any(keyword in lowered for keyword in SKIP_SECTION_KEYWORDS)


def parse_models_rst(text: str) -> list[ParsedModel]:
    lines = text.splitlines()
    rows: list[ParsedModel] = []
    current_section = ""
    skip_current = False

    for i, line in enumerate(lines):
        stripped = line.strip()
        if (
            stripped
            and len(set(stripped)) == 1
            and stripped[0] in SECTION_UNDERLINE_CHARS
            and i > 0
            and lines[i - 1].strip()
            and len(stripped) >= len(lines[i - 1].strip())
        ):
            current_section = lines[i - 1].strip()
            skip_current = should_skip_section(current_section)
            continue

        if skip_current or not current_section:
            continue

        match = HEF_URL_RE.search(line)
        if match:
            url = match.group(0)
            rows.append(
                ParsedModel(
                    section=current_section,
                    hef_filename=url.rsplit("/", 1)[-1],
                    url=url,
                )
            )
    return rows
