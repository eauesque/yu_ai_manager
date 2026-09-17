#!/usr/bin/env python3
"""Sync dev-overview.json → dev-overview.html.

Workflow:
1. If VERSION file exists and `version` in the JSON differs, update `version`
   and `last_synced` in dev-overview.json in-place (formatting preserved).
2. Embed the (possibly updated) JSON into the <script id="overview-data"> block
   inside dev-overview.html so the HTML works under file:// without a fetch.

Run after editing docs/development/dev-overview.json:
    python scripts/sync_dev_overview.py

Exit codes:
    0  All files up to date or successfully updated.
    1  Marker block missing or other I/O failure.
"""
from __future__ import annotations

import re
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = REPO_ROOT / "docs" / "development" / "dev-overview.json"
HTML_PATH = REPO_ROOT / "docs" / "development" / "dev-overview.html"
VERSION_PATH = REPO_ROOT / "VERSION"

MARKER_RE = re.compile(
    r'(<script id="overview-data" type="application/json">)(.*?)(</script>)',
    re.DOTALL,
)


def _set_top_level_str(raw: str, key: str, value: str) -> str:
    """Replace a top-level string field value without reformatting the JSON."""
    pattern = re.compile(r'(?m)^(\s*"' + re.escape(key) + r'"\s*:\s*)"[^"\\]*"')
    return pattern.sub(r'\g<1>"' + value + '"', raw, count=1)


def _sync_json() -> bool:
    """Update version/last_synced in the JSON if VERSION has changed.

    Returns True if the JSON file was rewritten.
    """
    if not VERSION_PATH.exists():
        return False

    current_version = VERSION_PATH.read_text(encoding="utf-8").strip()
    raw = JSON_PATH.read_text(encoding="utf-8")

    m = re.search(r'(?m)^\s*"version"\s*:\s*"([^"\\]*)"', raw)
    if m and m.group(1) == current_version:
        return False

    # Local calendar date, same value `date.today()` gave. Not
    # `now(UTC).date()`: under a positive offset that is yesterday.
    today = datetime.now(tz=UTC).astimezone().date().isoformat()
    raw = _set_top_level_str(raw, "version", current_version)
    raw = _set_top_level_str(raw, "last_synced", today)
    JSON_PATH.write_text(raw, encoding="utf-8")
    print(f"Updated dev-overview.json: version={current_version}, last_synced={today}.")
    return True


def _html_safe_json(raw: str) -> str:
    """Escape '<' as the JSON unicode escape \\u003c before embedding in HTML.

    Prevents "</script>" from closing the <script> tag and "<!--" from being
    parsed as an HTML comment. \\u003c is a valid JSON string escape that
    decoders restore to '<', so the round-trip is lossless.
    """
    return raw.replace("<", "\\u003c")


def _embed_into_html() -> int:
    """Embed dev-overview.json into the HTML marker block. Returns exit code."""
    json_text = _html_safe_json(JSON_PATH.read_text(encoding="utf-8").rstrip() + "\n")
    html_text = HTML_PATH.read_text(encoding="utf-8")

    if not MARKER_RE.search(html_text):
        print(
            'ERROR: <script id="overview-data" type="application/json"> block '
            "not found in dev-overview.html",
            file=sys.stderr,
        )
        return 1

    new_html = MARKER_RE.sub(
        lambda m: m.group(1) + "\n" + json_text + m.group(3),
        html_text,
        count=1,
    )

    if new_html == html_text:
        print("dev-overview.html already in sync.")
        return 0

    HTML_PATH.write_text(new_html, encoding="utf-8")
    print(f"Updated {HTML_PATH.relative_to(REPO_ROOT)}.")
    return 0


def main() -> int:
    if not JSON_PATH.exists():
        print(f"ERROR: missing {JSON_PATH}", file=sys.stderr)
        return 1
    if not HTML_PATH.exists():
        print(f"ERROR: missing {HTML_PATH}", file=sys.stderr)
        return 1

    _sync_json()
    return _embed_into_html()


if __name__ == "__main__":
    raise SystemExit(main())
