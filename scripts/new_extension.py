#!/usr/bin/env python3
# scripts/new_extension.py
"""Generate a new extension from the blueprint template.

Usage:
    uv run python scripts/new_extension.py <name> [--type simple|full] [--dry-run]

Example:
    uv run python scripts/new_extension.py my_feature
    uv run python scripts/new_extension.py my_feature --type simple --dry-run
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_TEMPLATE_DIR = _REPO / "docs" / "templates" / "extension_blueprint"
_PLACEHOLDER = "__EXTNAME__"


def to_snake_case(name: str) -> str:
    """Normalize extension name to snake_case."""
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    name = name.strip("_")
    return name


def get_template_files(ext_type: str) -> list[Path]:
    """Return list of template files to copy."""
    all_files = [
        _TEMPLATE_DIR / f"{_PLACEHOLDER}_ext.py",
        _TEMPLATE_DIR / "core_impl" / "_blueprint.py",
        _TEMPLATE_DIR / "core_impl" / "api_mutations.py",
        _TEMPLATE_DIR / "core_impl" / "api_queries.py",
        _TEMPLATE_DIR / "templates" / _PLACEHOLDER / "index.html",
    ]
    if ext_type == "simple":
        return [
            _TEMPLATE_DIR / "core_impl" / "api_mutations.py",
            _TEMPLATE_DIR / "core_impl" / "api_queries.py",
        ]
    return all_files


def replace_placeholder(text: str, name: str) -> str:
    return text.replace(_PLACEHOLDER, name)


def dest_path(template_file: Path, name: str, dest_dir: Path) -> Path:
    rel = template_file.relative_to(_TEMPLATE_DIR)
    rel_str = replace_placeholder(str(rel), name)
    return dest_dir / rel_str


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a new extension from template.")
    parser.add_argument("name", help="Extension name (will be normalized to snake_case)")
    parser.add_argument("--type", choices=["simple", "full"], default="full",
                        help="Template type: simple (API only) or full (default)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be created without writing files")
    args = parser.parse_args()

    name = to_snake_case(args.name)
    if not name:
        print(f"Error: invalid extension name '{args.name}'", file=sys.stderr)
        return 1

    dest_dir = _REPO / "extensions" / f"builtin_{name}"

    if dest_dir.exists() and not args.dry_run:
        print(f"Error: {dest_dir} already exists.", file=sys.stderr)
        return 1

    template_files = get_template_files(args.type)
    missing = [f for f in template_files if not f.exists()]
    if missing:
        print("Error: template files missing:", file=sys.stderr)
        for f in missing:
            print(f"  {f}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"[dry-run] Would create {dest_dir}/")
        for tf in template_files:
            dp = dest_path(tf, name, dest_dir)
            print(f"  {dp.relative_to(_REPO)}")
        return 0

    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / "core_impl").mkdir(exist_ok=True)
    (dest_dir / "templates" / name).mkdir(parents=True, exist_ok=True)
    (dest_dir / "core_impl" / "__init__.py").touch()

    created: list[Path] = []
    for tf in template_files:
        dp = dest_path(tf, name, dest_dir)
        dp.parent.mkdir(parents=True, exist_ok=True)
        content = replace_placeholder(tf.read_text(encoding="utf-8"), name)
        dp.write_text(content, encoding="utf-8")
        created.append(dp)

    print(f"✅ Created {dest_dir.relative_to(_REPO)}/")
    for f in created:
        print(f"   {f.relative_to(dest_dir)}")

    print("""
Next steps:
  1. Register your blueprint in the application factory
     (check existing extensions for the registration pattern)
  2. All POST/PUT/DELETE routes already have require_admin_scope() — keep it!
  3. Run: uv run python scripts/pre_push_check.py --skip ts,pyright,pytest
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
