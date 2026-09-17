#!/usr/bin/env python3
"""regex_debug.py — Test regex patterns against the tag database.

Usage:
    python tools/regex_debug.py PATTERN [--db data/tags.db] [--limit 20] [--case]
    python tools/regex_debug.py "1girl.*blue" --limit 5
    python tools/regex_debug.py "(?i)masterpiece" --field negative
    python tools/regex_debug.py "lora:.*:0\\.[5-9]" --field prompt

Options:
    PATTERN          Python regex to test (required)
    --db PATH        Database path (default: data/tags.db)
    --limit N        Max results to show (default: 20)
    --field FIELD    Search field: prompt, negative, both (default: both)
    --case           Case-sensitive matching (default: case-insensitive)
    --tags-only      Show matched tags instead of prompt lines
    --verbose        Show full prompt text (not truncated)
"""
import argparse
import os
import re
import sys
import time
from pathlib import Path

# Allow `python tools/regex_debug.py` to import from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# tags.db is SQLCipher-encrypted; route through the cipher shim and apply_key().
# Plaintext fallback supported for backups / test DBs via magic-header probe.
from core.services_core.db_cipher import apply_key, sqlite3  # noqa: E402
from core.services_core.db_migrate_encrypt import _is_plaintext  # noqa: E402


def main():
    parser = argparse.ArgumentParser(
        description="Test regex patterns against the tag database prompts."
    )
    parser.add_argument("pattern", help="Python regex pattern to test")
    parser.add_argument("--db", default="data/tags.db", help="Database path")
    parser.add_argument("--limit", type=int, default=20, help="Max results")
    parser.add_argument(
        "--field",
        choices=["prompt", "negative", "both"],
        default="both",
        help="Which field to search",
    )
    parser.add_argument("--case", action="store_true", help="Case-sensitive")
    parser.add_argument("--tags-only", action="store_true", help="Show tags")
    parser.add_argument("--verbose", action="store_true", help="Full prompt")
    args = parser.parse_args()

    # Validate pattern
    flags = 0 if args.case else re.IGNORECASE
    try:
        rx = re.compile(args.pattern, flags)
    except re.error as e:
        print(f"Invalid regex: {e}", file=sys.stderr)
        print(f"  Pattern: {args.pattern!r}", file=sys.stderr)
        sys.exit(1)

    # Open DB
    db_path = args.db
    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    if not _is_plaintext(Path(db_path)):
        apply_key(con)
    con.execute("PRAGMA query_only=ON")
    con.row_factory = sqlite3.Row

    # Count total templates
    try:
        total = con.execute("SELECT COUNT(*) FROM templates").fetchone()[0]
    except sqlite3.OperationalError:
        print("Error: 'templates' table not found. Is this a valid tags.db?", file=sys.stderr)
        con.close()
        sys.exit(1)
    print(f"Database: {db_path}  ({total} templates)")
    print(f"Pattern:  {args.pattern!r}  (flags: {'case-sensitive' if args.case else 'case-insensitive'})")
    print(f"Field:    {args.field}")
    print("-" * 60)

    # Scan
    t0 = time.perf_counter()
    rows = con.execute(
        "SELECT t.file_id, t.raw_prompt, t.raw_negative, f.path "
        "FROM templates t JOIN files f ON f.id = t.file_id "
        "WHERE f.is_deleted = 0"
    ).fetchall()

    matches = []
    for row in rows:
        prompt = row["raw_prompt"] or ""
        negative = row["raw_negative"] or ""

        hit_prompt = args.field in ("prompt", "both") and rx.search(prompt)
        hit_neg = args.field in ("negative", "both") and rx.search(negative)

        if hit_prompt or hit_neg:
            matches.append(
                {
                    "file_id": row["file_id"],
                    "path": row["path"],
                    "prompt": prompt,
                    "negative": negative,
                    "hit_prompt": bool(hit_prompt),
                    "hit_negative": bool(hit_neg),
                }
            )

    elapsed = time.perf_counter() - t0
    print(f"Scanned {len(rows)} templates in {elapsed:.2f}s  →  {len(matches)} matches")
    print()

    if not matches:
        print("No matches found.")
        con.close()
        return

    # Display
    shown = matches[: args.limit]
    for i, m in enumerate(shown, 1):
        path_short = m["path"]
        if len(path_short) > 70:
            path_short = "..." + path_short[-67:]
        print(f"[{i}] id={m['file_id']}  {path_short}")

        if args.tags_only:
            # Show matching substring only
            for field_name in ("prompt", "negative"):
                if not m[f"hit_{field_name.replace('prompt','prompt').replace('negative','negative')}"]:
                    continue
                text = m[field_name]
                found = rx.findall(text)
                if found:
                    print(f"    {field_name}: {found[:5]}")
        else:
            for field_name, hit_key in [("prompt", "hit_prompt"), ("negative", "hit_negative")]:
                if not m[hit_key]:
                    continue
                text = m[field_name]
                if not args.verbose and len(text) > 120:
                    # Show context around first match
                    match = rx.search(text)
                    if match:
                        start = max(0, match.start() - 30)
                        end = min(len(text), match.end() + 30)
                        snippet = text[start:end]
                        if start > 0:
                            snippet = "..." + snippet
                        if end < len(text):
                            snippet = snippet + "..."
                        text = snippet
                print(f"    {field_name}: {text}")
        print()

    if len(matches) > args.limit:
        print(f"... and {len(matches) - args.limit} more matches (use --limit to show more)")

    con.close()


if __name__ == "__main__":
    main()
