"""CLI entrypoint for diagnostics bug report generation."""

from __future__ import annotations

import argparse
from pathlib import Path

from core.diagnostics.bug_report import create_bug_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a diagnostics repair bug report folder.")
    parser.add_argument("--repair-root", default="repair", help="Directory where timestamped repair folders are created.")
    args = parser.parse_args(argv)
    repair_dir = create_bug_report(Path(args.repair_root))
    print(repair_dir)
    return 0
