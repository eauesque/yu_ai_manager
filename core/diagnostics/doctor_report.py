"""Report rendering for doctor diagnostics."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from core.diagnostics.doctor import CheckResult


def summarize(results: list[CheckResult]) -> dict[str, int]:
    return {
        "errors": sum(1 for result in results if result.status == "ERROR"),
        "warnings": sum(1 for result in results if result.status == "WARN"),
    }


def render_markdown(results: list[CheckResult]) -> str:
    summary = summarize(results)
    lines = [
        "# Environment Diagnosis",
        "",
        f"- Errors: {summary['errors']}",
        f"- Warnings: {summary['warnings']}",
        "",
        "| Status | Check | Fix hint |",
        "|---|---|---|",
    ]
    for result in results:
        message = result.message.replace("|", "\\|").replace("\n", " ")
        hint = (result.fix_hint or "").replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {result.status} | {message} | {hint} |")
    lines.append("")
    return "\n".join(lines)


def render_json(results: list[CheckResult]) -> dict[str, Any]:
    return {
        "schema": "yu://diagnostics/doctor/1",
        "created_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "summary": summarize(results),
        "results": [result.to_dict() for result in results],
    }


def write_report_files(report_dir: Path, report_md: str, report_json: dict[str, Any]) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    stem = f"doctor_{dt.datetime.now(tz=dt.UTC).astimezone().strftime('%Y%m%d-%H%M%S')}"
    md_path = report_dir / f"{stem}.md"
    json_path = report_dir / f"{stem}.json"
    suffix = 1
    while md_path.exists() or json_path.exists():
        md_path = report_dir / f"{stem}-{suffix}.md"
        json_path = report_dir / f"{stem}-{suffix}.json"
        suffix += 1
    md_path.write_text(report_md, encoding="utf-8")
    json_path.write_text(json.dumps(report_json, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return md_path, json_path
