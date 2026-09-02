"""CLI entrypoint for environment diagnosis reports."""

from __future__ import annotations

import os
from pathlib import Path

from core.diagnostics.doctor import PROJECT_ROOT, run_all_checks
from core.diagnostics.doctor_report import render_json, render_markdown, write_report_files
from core.services_core.db_api import init_app_state


def _default_db_path(project_root: Path) -> Path:
    return Path(os.environ.get("TAGDB_DB", project_root / "data" / "tags.db")).expanduser()


def write_doctor_reports(report_dir: Path | None = None, project_root: Path | None = None) -> tuple[Path, Path, dict]:
    root = (project_root or PROJECT_ROOT).resolve()
    db_path = _default_db_path(root)
    init_app_state(db_path, {})
    results = run_all_checks(project_root=root, db_path=db_path)
    report_json = render_json(results)
    report_md = render_markdown(results)
    out_dir = report_dir or root / "reports"
    md_path, json_path = write_report_files(out_dir, report_md, report_json)
    return md_path, json_path, report_json


def main() -> int:
    md_path, json_path, report_json = write_doctor_reports()
    summary = report_json["summary"]
    print(f"Wrote {md_path}")
    print(f"Wrote {json_path}")
    print(f"Errors: {summary['errors']}, Warnings: {summary['warnings']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
