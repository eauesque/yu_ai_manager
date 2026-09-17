"""Line-count policy reporter for implementation code.

This script reports implementation files that exceed the project's
line-count thresholds and can enforce the current policy baseline.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

SOURCE_ROOTS = (
    "core",
    "routes",
    "mcp_server",
    "src/ts",
    "extensions",
    "src-tauri/src",
    "cli",
)

ALLOWED_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".css", ".rs"}

WARNING_THRESHOLD = 300
ACTION_THRESHOLD = 500
CRITICAL_THRESHOLD = 800

# Current baseline as of 2026-06-01.
ALLOWED_OVER_500 = {
    "extensions/builtin_comfyui_bridge/core_impl/comfyui_api_generate.py",
    "routes/gateway_backends.py",
    # Crossed 500 in 9e8b7ba48 (an overall deadline on four outbound routes).
    "routes/wd_tagger_admin_routes.py",
    "src/ts/apps/crypto-tools-app.ts",
    "src/ts/crypto/subtle_ops.ts",
    "src/ts/shared/json-editor-enhance.ts",
    "src/ts/tools-page/wd-tagger/profile-form.ts",
    "src/ts/tools-page/wd-tagger/profile-list.ts",
}

ALLOWED_OVER_800 = {
    "src/ts/tools-page/wd-tagger/profile-form.ts",
}


@dataclass(frozen=True)
class FileStat:
    path: str
    lines: int


def iter_source_files(root: Path = REPO) -> list[Path]:
    files: list[Path] = []
    for base in SOURCE_ROOTS:
        base_path = root / base
        if not base_path.exists():
            continue
        for path in base_path.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in ALLOWED_SUFFIXES:
                continue
            files.append(path)
    return sorted(files)


def count_lines(path: Path) -> int:
    with path.open("r", encoding="utf-8") as fh:
        return sum(1 for _ in fh)


def collect_stats(root: Path = REPO) -> list[FileStat]:
    stats = []
    for path in iter_source_files(root):
        rel = str(path.relative_to(root)).replace("\\", "/")
        stats.append(FileStat(path=rel, lines=count_lines(path)))
    return sorted(stats, key=lambda item: (-item.lines, item.path))


def bucketize(stats: list[FileStat]) -> dict[str, list[FileStat]]:
    return {
        "gt_300": [item for item in stats if item.lines > WARNING_THRESHOLD],
        "gt_500": [item for item in stats if item.lines > ACTION_THRESHOLD],
        "gt_800": [item for item in stats if item.lines > CRITICAL_THRESHOLD],
    }


def evaluate_policy(stats: list[FileStat]) -> list[str]:
    violations: list[str] = []
    over_500 = {item.path: item.lines for item in stats if item.lines > ACTION_THRESHOLD}
    over_800 = {item.path: item.lines for item in stats if item.lines > CRITICAL_THRESHOLD}

    unexpected_500 = sorted(set(over_500) - ALLOWED_OVER_500)
    unexpected_800 = sorted(set(over_800) - ALLOWED_OVER_800)
    stale_500 = sorted(ALLOWED_OVER_500 - set(over_500))
    stale_800 = sorted(ALLOWED_OVER_800 - set(over_800))

    for path in unexpected_500:
        violations.append(f"new >500 file: {path} ({over_500[path]} lines)")
    for path in unexpected_800:
        violations.append(f"new >800 file: {path} ({over_800[path]} lines)")
    for path in stale_500:
        violations.append(f"remove from ALLOWED_OVER_500 baseline: {path}")
    for path in stale_800:
        violations.append(f"remove from ALLOWED_OVER_800 baseline: {path}")

    return violations


def build_text_report(stats: list[FileStat]) -> str:
    buckets = bucketize(stats)
    lines = [
        "Line Count Report",
        f"Source roots: {', '.join(SOURCE_ROOTS)}",
        f">300: {len(buckets['gt_300'])}",
        f">500: {len(buckets['gt_500'])}",
        f">800: {len(buckets['gt_800'])}",
        "",
    ]

    for label, items in (
        (">800", buckets["gt_800"]),
        (">500", buckets["gt_500"]),
        (">300", buckets["gt_300"][:50]),
    ):
        lines.append(label)
        if not items:
            lines.append("  (none)")
        else:
            for item in items:
                lines.append(f"  {item.lines:>4}  {item.path}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def build_json_report(stats: list[FileStat]) -> str:
    buckets = bucketize(stats)
    payload = {
        "thresholds": {
            "warning": WARNING_THRESHOLD,
            "action": ACTION_THRESHOLD,
            "critical": CRITICAL_THRESHOLD,
        },
        "counts": {
            "gt_300": len(buckets["gt_300"]),
            "gt_500": len(buckets["gt_500"]),
            "gt_800": len(buckets["gt_800"]),
        },
        "files": {
            key: [item.__dict__ for item in value]
            for key, value in buckets.items()
        },
        "policy_violations": evaluate_policy(stats),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero when the current >500/>800 baseline is violated",
    )
    args = parser.parse_args(argv)

    stats = collect_stats()
    if args.json:
        sys.stdout.write(build_json_report(stats))
    else:
        sys.stdout.write(build_text_report(stats))

    if not args.check:
        return 0

    violations = evaluate_policy(stats)
    if violations:
        for violation in violations:
            print(f"POLICY: {violation}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
