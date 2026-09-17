"""Create diagnostics bug report repair folders."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from quart import current_app

from core.diagnostics.environment import build_environment_snapshot
from core.diagnostics.logs import collect_recent_logs
from core.diagnostics.redaction import (
    compute_warnings,
    counts_to_report,
    merge_counts,
    redact_dict,
    redact_text,
)
from core.diagnostics.ui_actions import dump_jsonl
from core.repair.generate_prompt import (
    copy_policy_files,
    generate_claude_prompt,
    generate_codex_prompt,
    write_repair_templates,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _timestamp() -> str:
    return dt.datetime.now(tz=dt.UTC).astimezone().strftime("%Y%m%d-%H%M%S")


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_text_if_exists(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _file_digest_entries(repair_dir: Path, *, exclude: set[str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted(repair_dir.iterdir()):
        if not path.is_file() or path.name in exclude:
            continue
        data = path.read_bytes()
        entries.append(
            {
                "name": path.name,
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    return entries


def _app_config() -> dict[str, Any]:
    try:
        return dict(current_app.config)
    except RuntimeError:
        return {}


def create_bug_report(repair_root: Path) -> Path:
    repair_root.mkdir(parents=True, exist_ok=True)
    repair_dir = repair_root / _timestamp()
    suffix = 1
    while repair_dir.exists():
        repair_dir = repair_root / f"{_timestamp()}-{suffix}"
        suffix += 1
    repair_dir.mkdir(parents=True)

    counts: dict[str, int] = {}
    touched: list[Path] = []

    env_counts: dict[str, int] = {}
    try:
        snapshot = build_environment_snapshot(_app_config())
    except TypeError:
        snapshot = build_environment_snapshot()
    environment = redact_dict(snapshot, env_counts)
    merge_counts(counts, env_counts)
    _write_json(repair_dir / "environment.redacted.json", environment)
    touched.append(repair_dir / "environment.redacted.json")

    recent_log, log_counts = collect_recent_logs(_PROJECT_ROOT)
    merge_counts(counts, log_counts)
    (repair_dir / "recent.redacted.log").write_text(recent_log, encoding="utf-8")
    touched.append(repair_dir / "recent.redacted.log")

    ui_actions, ui_counts = redact_text(dump_jsonl())
    merge_counts(counts, ui_counts)
    (repair_dir / "ui_actions.redacted.jsonl").write_text(ui_actions, encoding="utf-8")
    touched.append(repair_dir / "ui_actions.redacted.jsonl")

    config_counts: dict[str, int] = {}
    from core.configuration.json_rw import candidate_config_paths, load_config_json

    config_path = next(
        (_PROJECT_ROOT / path for path in candidate_config_paths() if (_PROJECT_ROOT / path).exists()), None
    )
    if config_path and config_path.exists():
        try:
            config_data = load_config_json(str(config_path))
            config_redacted = redact_dict(config_data, config_counts)
            _write_json(repair_dir / "config.redacted.json", config_redacted)
        except Exception:
            config_text, local_counts = redact_text(_read_text_if_exists(config_path))
            merge_counts(config_counts, local_counts)
            (repair_dir / "config.redacted.json").write_text(config_text, encoding="utf-8")
    else:
        _write_json(repair_dir / "config.redacted.json", {})
    merge_counts(counts, config_counts)
    touched.append(repair_dir / "config.redacted.json")

    launch_args_text, launch_counts = redact_text(_read_text_if_exists(_PROJECT_ROOT / "launch-args.txt"))
    merge_counts(counts, launch_counts)
    (repair_dir / "launch_args.redacted.txt").write_text(launch_args_text, encoding="utf-8")
    touched.append(repair_dir / "launch_args.redacted.txt")

    bug_report = f"""# Bug Report

Created at: {dt.datetime.now(dt.UTC).isoformat(timespec="seconds")}

## User Notes

Describe what happened here before sending the repair folder.
"""
    (repair_dir / "BUG_REPORT.md").write_text(bug_report, encoding="utf-8")

    copy_policy_files(repair_dir)
    generate_codex_prompt(repair_dir)
    generate_claude_prompt(repair_dir)
    write_repair_templates(repair_dir)

    warnings = compute_warnings(touched)
    redaction_report = {"redacted": counts_to_report(counts), "warnings": warnings}
    _write_json(repair_dir / "redaction_report.json", redaction_report)

    # manifest.json must list every other file with its SHA-256 so the AI
    # repair agent can detect post-bundle tampering (untrusted-input gate
    # required by AI_REPAIR_POLICY policy_version >= 2).
    manifest = {
        "schema": "yu://diagnostics/bug-report/2",
        "created_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "policy_version_required": 2,
        "files": _file_digest_entries(repair_dir, exclude={"manifest.json"}),
    }
    _write_json(repair_dir / "manifest.json", manifest)
    return repair_dir


def default_repair_root() -> Path:
    try:
        from core.paths import data_path  # noqa: PLC0415

        return data_path("repair")
    except Exception:
        return _PROJECT_ROOT / "repair"


def copy_tree_to_repair(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
