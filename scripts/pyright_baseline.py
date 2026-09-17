"""Generate or update tools/pyright_baseline.json from current pyright output.

Baseline is per-file error count keyed by `file_relpath -> count`. Future
pre-push checks compare per-file counts: if a changed file has MORE errors
than its baseline, the change introduces new hallucinations.

Run via:
    venv/Scripts/python scripts/pyright_baseline.py [--out path]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO / "tools" / "pyright_baseline.json"
PY = (REPO / "venv" / "Scripts" / "python.exe")
if not PY.exists():
    PY = REPO / "venv" / "bin" / "python"


def run_pyright() -> dict:
    proc = subprocess.run(
        [str(PY), "-m", "pyright", "--outputjson"],
        cwd=REPO, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=900,
    )
    if not proc.stdout:
        raise RuntimeError(f"pyright returned no JSON\nstderr:\n{proc.stderr[:1000]}")
    return json.loads(proc.stdout)


def build_baseline(report: dict) -> dict:
    """Per-file error count + total."""
    counts: Counter[str] = Counter()
    for diag in report.get("generalDiagnostics", []):
        if diag.get("severity") != "error":
            continue
        f = diag.get("file", "")
        if not f:
            continue
        try:
            rel = str(Path(f).resolve().relative_to(REPO)).replace("\\", "/")
        except ValueError:
            rel = f.replace("\\", "/")
        counts[rel] += 1

    summary = report.get("summary", {})
    return {
        "schema": 1,
        "generated_with": "scripts/pyright_baseline.py",
        "summary": {
            "files_analyzed": summary.get("filesAnalyzed", 0),
            "total_errors": summary.get("errorCount", 0),
            "total_warnings": summary.get("warningCount", 0),
        },
        "files": dict(sorted(counts.items())),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    print("Running pyright (this takes ~1-3 minutes)...")
    report = run_pyright()
    baseline = build_baseline(report)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(baseline, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    s = baseline["summary"]
    print(
        f"Wrote {out_path}\n"
        f"  files_analyzed = {s['files_analyzed']}\n"
        f"  files_with_errors = {len(baseline['files'])}\n"
        f"  total_errors = {s['total_errors']}\n"
        f"  total_warnings = {s['total_warnings']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
