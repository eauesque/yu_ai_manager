"""Evaluate a structural_validator criteria yml against a subject yml.

Usage:
    uv run python scripts/run_criteria.py <checker_yml> <subject_yml>

    checker_yml: path relative to repo root, must be yml_type: structural_validator
    subject_yml: path relative to repo root, the criteria yml being validated

Exit codes:
    0  all criteria pass
    1  one or more criteria fail or evaluation error
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_front_matter(md_path: Path) -> dict:
    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end = None
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            end = i
            break
    if end is None:
        return {}
    return yaml.safe_load("\n".join(lines[1:end])) or {}


def _section_exists(md_path: Path, heading: str) -> bool:
    text = md_path.read_text(encoding="utf-8")
    pattern = r"^" + re.escape(heading) + r"\s*$"
    return bool(re.search(pattern, text, re.MULTILINE))


def _parse_args(raw: str) -> list:
    """Parse 'yml, "key"' or 'yml, "key", ["v1", "v2"]' into a list."""
    args: list = []
    i = 0
    while i < len(raw):
        while i < len(raw) and raw[i] in " ,\t":
            i += 1
        if i >= len(raw):
            break
        if raw[i] == '"':
            j = i + 1
            while j < len(raw) and raw[j] != '"':
                j += 1
            args.append(raw[i + 1 : j])
            i = j + 1
        elif raw[i] == "[":
            try:
                j = raw.index("]", i)
            except ValueError:
                break  # unclosed '[' — stop parsing, return what we have
            items = [s.strip().strip('"') for s in raw[i + 1 : j].split(",") if s.strip()]
            args.append(items)
            i = j + 1
        else:
            j = i
            while j < len(raw) and raw[j] not in ' ,"[]':
                j += 1
            args.append(raw[i:j])
            i = j
    return args


def _eval_predicate(
    predicate: str,
    subject_yml: dict,
    md_path: Path | None,
) -> tuple[bool, str]:
    """Evaluate a check: predicate. Returns (passed, detail)."""
    m = re.match(r"(\w+)\((.+)\)$", predicate.strip(), re.DOTALL)
    if not m:
        return False, f"invalid predicate syntax: {predicate!r}"
    func_name, raw_args = m.group(1), m.group(2)
    args = _parse_args(raw_args)
    if not args:
        return False, f"cannot parse args: {raw_args!r}"

    target_name = args[0]

    if func_name == "section_exists":
        if md_path is None:
            return False, "section_exists: md not resolved"
        heading = args[1] if len(args) > 1 else ""
        result = _section_exists(md_path, heading)
        return result, f"section_exists(md, {heading!r}) = {result}"

    if target_name == "yml":
        data = subject_yml
    elif target_name == "md":
        if md_path is None:
            return False, "target:md but rationale_ref not resolved"
        data = _load_front_matter(md_path)
    else:
        return False, f"unknown target: {target_name!r}"

    key = args[1] if len(args) > 1 else ""

    if func_name == "field_exists":
        result = key in data
        return result, f"field_exists({target_name}, {key!r}) → {result}"

    elif func_name == "field_in_enum":
        allowed = args[2] if len(args) > 2 else []
        val = data.get(key)
        result = val in allowed
        return result, f"field_in_enum({target_name}, {key!r}, {allowed}) → {val!r} pass={result}"

    elif func_name == "field_matches":
        pattern = args[2] if len(args) > 2 else ""
        val = str(data.get(key) or "")
        result = bool(re.search(pattern, val))
        return result, f"field_matches({target_name}, {key!r}, {pattern!r}) → {val!r} pass={result}"

    elif func_name == "field_not_pattern":
        pattern = args[2] if len(args) > 2 else ""
        val = str(data.get(key) or "")
        result = not bool(re.search(pattern, val))
        return result, f"field_not_pattern({target_name}, {key!r}, {pattern!r}) → {val!r} pass={result}"

    return False, f"unknown predicate: {func_name!r}"


def run(checker_path: Path, subject_path: Path) -> tuple[bool, list[tuple[str, bool, str]], str]:
    """Return (overall_pass, [(criterion_id, passed, detail), ...], aggregation)."""
    checker = yaml.safe_load(checker_path.read_text(encoding="utf-8"))
    subject = yaml.safe_load(subject_path.read_text(encoding="utf-8"))

    if not isinstance(checker, dict) or checker.get("yml_type") != "structural_validator":
        return False, [("_", False, "checker must be yml_type: structural_validator")], "all_must_pass"

    md_path: Path | None = None
    if ref := (subject or {}).get("rationale_ref"):
        candidate = _REPO_ROOT / ref
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = None
        if resolved is not None and resolved.is_relative_to(_REPO_ROOT.resolve()) and resolved.exists():
            md_path = resolved

    results: list[tuple[str, bool, str]] = []
    for c in checker.get("criteria", []):
        cid = c.get("id", "?")
        check = c.get("check", "")
        if not check:
            results.append((cid, True, "no check: field — skipped"))
            continue
        passed, detail = _eval_predicate(check, subject or {}, md_path)
        results.append((cid, passed, detail))

    aggregation = checker.get("aggregation", "all_must_pass")
    pass_count = sum(1 for _, p, _ in results if p)
    if aggregation == "majority":
        overall = pass_count > len(results) / 2
    elif aggregation == "any_blocks":
        overall = all(p for _, p, _ in results)
    else:  # all_must_pass (default)
        overall = all(p for _, p, _ in results)

    return overall, results, aggregation


def main() -> int:
    if len(sys.argv) != 3:
        print(f"Usage: {Path(sys.argv[0]).name} <checker_yml> <subject_yml>", file=sys.stderr)
        return 1
    checker_path = _REPO_ROOT / sys.argv[1]
    subject_path = _REPO_ROOT / sys.argv[2]
    for p in (checker_path, subject_path):
        if not p.exists():
            print(f"ERROR: not found: {p}", file=sys.stderr)
            return 1

    overall, results, agg = run(checker_path, subject_path)

    print(f"\n=== run_criteria: {sys.argv[1]} → {sys.argv[2]} ===")
    for cid, passed, detail in results:
        print(f"  [{'PASS' if passed else 'FAIL'}] {cid}: {detail}")
    print(f"\nResult: {'PASS' if overall else 'FAIL'} (aggregation={agg})")
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
