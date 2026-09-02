"""doc-format-charter 構造バリデーター (V-1a / V-1b / V-1c / V-2 / V-4)。

各関数は (ok: bool, message: str) を返す。
"""
from __future__ import annotations

import re as _re
from pathlib import Path
from typing import Any

import yaml


def _load_yaml(path: Path) -> dict | None:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None


def _is_flat_kv_guard(when: Any) -> bool:
    """when 値が flat key-value equality マップ（V-1c 合法形式）か判定する。

    合法: dict で全値がスカラー（str/int/bool）かつ null でない。
    不正: 文字列式、nested mapping、sequence、null 値。
    """
    if not isinstance(when, dict):
        return False
    for v in when.values():
        if v is None:
            return False
        if not isinstance(v, (str, int, bool)):
            return False
    return True


def _guards_compatible(g1: dict, g2: dict) -> bool:
    """二つの flat kv guard が両立する（共通 case が存在する）か判定する。"""
    shared_keys = set(g1) & set(g2)
    return all(g1[k] == g2[k] for k in shared_keys)


def _guard_includes(g_specific: dict, g_general: dict) -> bool:
    """g_specific ⊇ g_general (g_specific が g_general より特異) か判定する。"""
    if len(g_specific) <= len(g_general):
        return False
    return all(g_specific.get(k) == v for k, v in g_general.items())


def check_default_arms(yaml_path: Path) -> tuple[bool, str]:
    """V-1a: match を持つ yaml に _default arm が存在するか検査する。"""
    data = _load_yaml(yaml_path)
    if data is None:
        return False, f"yaml parse error: {yaml_path}"
    match = data.get("match")
    if match is None:
        return True, "no match section (skip)"
    if "_default" not in match:
        return False, f"V-1a: match._default が存在しない: {yaml_path}"
    return True, "V-1a: OK"


def check_guard_conformance(yaml_path: Path) -> tuple[bool, str]:
    """V-1c: match.branches の全 when: 値が flat kv equality マップか検査する。"""
    data = _load_yaml(yaml_path)
    if data is None:
        return False, f"yaml parse error: {yaml_path}"
    match = data.get("match")
    if match is None:
        return True, "no match section (skip)"
    branches = match.get("branches", [])
    for i, branch in enumerate(branches):
        when = branch.get("when")
        if when is None:
            return False, f"V-1c: branches[{i}] に when: がない: {yaml_path}"
        if not _is_flat_kv_guard(when):
            return False, (
                f"V-1c: branches[{i}].when が flat kv equality マップでない: "
                f"{when!r} in {yaml_path}"
            )
    return True, "V-1c: OK"


def check_guard_inclusion(yaml_path: Path) -> tuple[bool, str]:
    """V-1b: guard の重なり・包含・順序を検査する（V-1c 通過後に実行）。

    reject 条件:
    1. 完全一致重複
    2. 両立かつ包含 (一般が特異より前)
    3. 両立かつ比較不能な重なり
    """
    data = _load_yaml(yaml_path)
    if data is None:
        return False, f"yaml parse error: {yaml_path}"
    match = data.get("match")
    if match is None:
        return True, "no match section (skip)"
    branches = match.get("branches", [])
    guards = [b.get("when", {}) for b in branches]

    for i in range(len(guards)):
        for j in range(i + 1, len(guards)):
            g1, g2 = guards[i], guards[j]
            if not _guards_compatible(g1, g2):
                continue
            if g1 == g2:
                return False, (
                    f"V-1b(1): 完全一致重複 branches[{i}] と [{j}]: "
                    f"{g1!r} in {yaml_path}"
                )
            g1_includes_g2 = _guard_includes(g1, g2)
            g2_includes_g1 = _guard_includes(g2, g1)
            if g2_includes_g1:
                return False, (
                    f"V-1b(2): 順序違反 — branches[{i}](一般:{g1!r}) が "
                    f"branches[{j}](特異:{g2!r}) より前: {yaml_path}"
                )
            if g1_includes_g2:
                continue
            return False, (
                f"V-1b(3): 比較不能な重なり — branches[{i}]:{g1!r} と "
                f"branches[{j}]:{g2!r} は両立するが互いに包含でない: {yaml_path}"
            )

    return True, "V-1b: OK"


_V2_PATTERNS = [
    _re.compile(r"もし.+ならば"),
    _re.compile(r".+の場合は"),
    _re.compile(r".+の場合に限り"),
    _re.compile(r"^例外[:：]"),
    _re.compile(r"^ただし"),
    _re.compile(r"^except when", _re.IGNORECASE),
    _re.compile(r"^unless ", _re.IGNORECASE),
]
_CASE_ITEM = _re.compile(r"^[-*]\s+.+の場合[:：]")


def check_stranded_procedures(md_path: Path, yaml_path: Path) -> tuple[bool, str]:
    """V-2: MD に条件/例外列挙構造があるのに yaml に criteria/match がない場合に warning を返す。

    Returns (True, warning_message) if stranded procedures detected.
    Returns (True, "") if no issues.
    """
    md_text = md_path.read_text(encoding="utf-8")
    data = _load_yaml(yaml_path)

    has_structured = bool(data and (data.get("criteria") or data.get("match")))
    if has_structured:
        return True, ""

    lines = md_text.splitlines()
    case_run = 0
    warnings: list[str] = []
    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        for pat in _V2_PATTERNS:
            if pat.search(stripped):
                warnings.append(f"  L{lineno}: {stripped[:60]}")
                break
        if _CASE_ITEM.match(stripped):
            case_run += 1
            if case_run >= 2:
                warnings.append(f"  L{lineno}: 場合分け箇条書き連続 ({case_run}項目目)")
        else:
            case_run = 0

    if warnings:
        msg = (
            f"V-2 WARNING: {md_path.name} に条件/例外列挙構造が見つかりましたが "
            f"{yaml_path.name} に criteria/match がありません。\n"
            + "\n".join(warnings[:5])
        )
        return True, msg
    return True, ""


def _resolve_rationale_ref(ref: str, repo_root: Path) -> tuple[Path | None, str | None]:
    """rationale_ref を (file_path, fragment) に分解する。"""
    if "#" in ref:
        path_str, fragment = ref.split("#", 1)
        return repo_root / path_str, fragment
    return repo_root / ref, None


def check_rationale_refs(yaml_path: Path, repo_root: Path) -> tuple[bool, str]:
    """V-4: yaml 内の rationale_ref が実在するアンカーを指しているか検査する。"""
    import sys

    scripts_dir = str(repo_root / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from build_charter_yaml import extract_anchors  # noqa: PLC0415

    data = _load_yaml(yaml_path)
    if data is None:
        return False, f"yaml parse error: {yaml_path}"

    refs: list[str] = []
    match = data.get("match") or {}
    default = match.get("_default") or {}
    if default.get("rationale_ref"):
        refs.append(default["rationale_ref"])
    for item in data.get("out_of_scope", []):
        if item.get("rationale_ref"):
            refs.append(item["rationale_ref"])
    for item in data.get("requires_rationale_when", []):
        if item.get("rationale_ref"):
            refs.append(item["rationale_ref"])

    for ref in refs:
        file_path, fragment = _resolve_rationale_ref(ref, repo_root)
        if file_path is None or not file_path.exists():
            return False, f"V-4: rationale_ref のファイルが存在しない: {ref!r}"
        if fragment:
            anchors = extract_anchors(file_path)
            if fragment not in anchors:
                return False, (
                    f"V-4: rationale_ref のアンカー '{fragment}' が "
                    f"{file_path.name} に存在しない: {ref!r}"
                )
    return True, "V-4: OK"
