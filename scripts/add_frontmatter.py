"""Insert doc_type: standalone_prior front-matter into docs that lack front-matter.

Run once during migration:
    uv run python scripts/add_frontmatter.py [--dry-run]

Skips files that already have YAML front-matter (first line '---' + second line
matches 'key: value' pattern). The initial 127 target docs have no front-matter,
so this skip is a safety guard for re-runs only.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DOCS_DIR = _REPO_ROOT / "docs" / "development" / "development_docs"
_YAML_KEY_PATTERN = re.compile(r"^[A-Za-z_][\w]*\s*:")
_FRONT_MATTER = "---\ndoc_type: standalone_prior\n---\n"


def has_front_matter(text: str) -> bool:
    lines = text.splitlines()
    if len(lines) < 2:
        return False
    return lines[0].strip() == "---" and bool(_YAML_KEY_PATTERN.match(lines[1]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print what would be changed without writing")
    args = parser.parse_args()

    inserted = 0
    skipped = 0
    for md_file in sorted(_DOCS_DIR.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        if has_front_matter(text):
            skipped += 1
            continue
        new_text = _FRONT_MATTER + text
        if args.dry_run:
            print(f"  [DRY] {md_file.name}")
        else:
            md_file.write_text(new_text, encoding="utf-8")
        inserted += 1

    action = "Would insert" if args.dry_run else "Inserted"
    print(f"{action} front-matter: {inserted} file(s), skipped: {skipped} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
