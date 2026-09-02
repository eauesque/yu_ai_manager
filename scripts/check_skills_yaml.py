"""YAML スキルファイルの構造検証と索引整合チェック。

検証: uv run python scripts/check_skills_yaml.py

チェック内容:
  1. yaml_validate  : .claude/commands/yaml/*.yaml が _schema.yaml の required フィールドを満たすか
  2. index_consistency: skills-index.yaml の local_yaml エントリに spec が存在するか
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
_YAML_DIR = _REPO_ROOT / ".claude" / "commands" / "yaml"
_SCHEMA_FILENAME = "_schema.yaml"
_INDEX = _REPO_ROOT / ".claude" / "skills-index.yaml"

_ALLOWED_ON_FAILURE = frozenset({"abort", "skip", "fallback"})
_ALLOWED_PRIORITY = frozenset({"high", "normal", "low"})
_ALLOWED_THEN = frozenset({"abort", "skip", "fallback"})


def _check_nonempty_str(val: object, label: str, problems: list[str]) -> bool:
    """val が非空文字列であることを確認し、問題があれば problems に追記して False を返す。"""
    if not isinstance(val, str) or not val.strip():
        problems.append(f"{label} は非空文字列必須（got: {val!r}）")
        return False
    return True


def validate_yaml_skills(yaml_dir: Path | None = None) -> tuple[bool, list[str]]:
    """各スキル YAML が必須フィールドを満たすかを検証する。"""
    if yaml_dir is None:
        yaml_dir = _YAML_DIR

    if not yaml_dir.exists():
        return True, []

    problems: list[str] = []

    for path in sorted(yaml_dir.glob("*.yaml")):
        if path.name == _SCHEMA_FILENAME:
            continue

        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            problems.append(f"{path.name}: YAML パースエラー — {e}")
            continue

        stem = path.stem
        prefix = path.name

        # ── meta ────────────────────────────────────────────────────
        meta = data.get("meta")
        if not isinstance(meta, dict):
            problems.append(f"{prefix}: meta フィールド必須")
            continue

        _check_nonempty_str(meta.get("name"), f"{prefix}: meta.name", problems)

        if meta.get("name") and meta["name"] != stem:
            problems.append(
                f"{prefix}: meta.name ({meta['name']!r}) がファイル名 stem ({stem!r}) と不一致"
            )

        # triggers: 非空リスト かつ 各要素が非空文字列
        triggers = meta.get("triggers")
        if not isinstance(triggers, list) or len(triggers) == 0:
            problems.append(f"{prefix}: meta.triggers は非空リスト必須")
        else:
            for j, t in enumerate(triggers):
                if not isinstance(t, str) or not t.strip():
                    problems.append(
                        f"{prefix}: meta.triggers[{j}] は非空文字列必須（got: {t!r}）"
                    )

        priority = meta.get("priority")
        if priority is not None and priority not in _ALLOWED_PRIORITY:
            problems.append(
                f"{prefix}: meta.priority の値 {priority!r} が不正"
                f"（許可値: {sorted(_ALLOWED_PRIORITY)}）"
            )

        # ── steps ───────────────────────────────────────────────────
        steps = data.get("steps")
        if not isinstance(steps, list) or len(steps) == 0:
            problems.append(f"{prefix}: steps は非空リスト必須")
            continue

        step_ids: set[str] = set()
        uses_fallback = False

        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                problems.append(f"{prefix}: steps[{i}] は dict 必須")
                continue

            # id / label は非空文字列必須
            for field in ("id", "label"):
                _check_nonempty_str(step.get(field), f"{prefix}: steps[{i}].{field}", problems)

            # action は文字列（block scalar も含む）必須
            action = step.get("action")
            if action is None:
                problems.append(f"{prefix}: steps[{i}].action は必須")
            elif not isinstance(action, str):
                problems.append(
                    f"{prefix}: steps[{i}].action は文字列必須（got: {type(action).__name__}）"
                )
            elif not action.strip():
                problems.append(f"{prefix}: steps[{i}].action は非空必須")

            # id の重複チェック
            step_id = step.get("id")
            if isinstance(step_id, str):
                if step_id in step_ids:
                    problems.append(f"{prefix}: steps id {step_id!r} が重複")
                step_ids.add(step_id)

            # on_failure の値域チェック
            on_failure = step.get("on_failure", "abort")
            if on_failure not in _ALLOWED_ON_FAILURE:
                problems.append(
                    f"{prefix}: steps[{i}].on_failure の値 {on_failure!r} が不正"
                    f"（許可値: {sorted(_ALLOWED_ON_FAILURE)}）"
                )
            if on_failure == "fallback":
                uses_fallback = True

            # depends_on: リスト かつ 各要素が既知の step_id を参照（後方参照は許容）
            depends_on = step.get("depends_on")
            if depends_on is not None:
                if not isinstance(depends_on, list):
                    problems.append(f"{prefix}: steps[{i}].depends_on はリスト必須")
                else:
                    # 全 step_ids が揃った後の検証は後段で行う（前方参照許容のため収集のみ）
                    pass

        # depends_on の参照先が実在する step_id であるかを全 step 収集後に検証
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            depends_on = step.get("depends_on")
            if isinstance(depends_on, list):
                for ref in depends_on:
                    if not isinstance(ref, str):
                        problems.append(
                            f"{prefix}: steps[{i}].depends_on の要素は文字列必須（got: {ref!r}）"
                        )
                    elif ref not in step_ids:
                        problems.append(
                            f"{prefix}: steps[{i}].depends_on で参照する id {ref!r} が存在しない"
                        )

        # ── conditions（省略可）──────────────────────────────────────
        # fallback チェックより先に処理し、then:fallback も uses_fallback に反映させる
        conditions = data.get("conditions")
        if conditions is not None:
            if not isinstance(conditions, list):
                problems.append(f"{prefix}: conditions はリスト必須（省略可）")
            else:
                for i, cond in enumerate(conditions):
                    if not isinstance(cond, dict):
                        problems.append(f"{prefix}: conditions[{i}] は dict 必須")
                        continue
                    # if: 非空文字列必須
                    _check_nonempty_str(
                        cond.get("if"), f"{prefix}: conditions[{i}].if", problems
                    )
                    # then: enum 値域チェック
                    then_val = cond.get("then")
                    if then_val is None:
                        problems.append(f"{prefix}: conditions[{i}].then は必須")
                    elif then_val not in _ALLOWED_THEN:
                        problems.append(
                            f"{prefix}: conditions[{i}].then の値 {then_val!r} が不正"
                            f"（許可値: {sorted(_ALLOWED_THEN)}）"
                        )
                    # conditions.then:fallback も fallback ブロックを必要とする
                    elif then_val == "fallback":
                        uses_fallback = True

        # steps.on_failure:fallback または conditions.then:fallback があれば fallback ブロック必須
        fallback = data.get("fallback")
        if uses_fallback and not isinstance(fallback, list):
            problems.append(
                f"{prefix}: on_failure/conditions.then に fallback があるが fallback ブロックがない"
            )

        # fallback ブロックの各項目を検証
        if isinstance(fallback, list):
            for i, fb in enumerate(fallback):
                if not isinstance(fb, dict):
                    problems.append(f"{prefix}: fallback[{i}] は dict 必須")
                    continue
                for field in ("condition", "action"):
                    if fb.get(field) is None:
                        problems.append(f"{prefix}: fallback[{i}].{field} は必須")

    return not problems, problems


def validate_index_consistency(
    index: Path | None = None,
    repo_root: Path | None = None,
) -> tuple[bool, list[str]]:
    """skills-index.yaml の local_yaml エントリに spec が存在するかを検証する。"""
    if index is None:
        index = _INDEX
    if repo_root is None:
        repo_root = _REPO_ROOT

    if not index.exists():
        return True, []

    try:
        data = yaml.safe_load(index.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        return False, [f"skills-index.yaml パースエラー — {e}"]

    problems: list[str] = []

    for entry in data.get("skills", []):
        if not isinstance(entry, dict):
            continue
        if entry.get("source") != "local_yaml":
            continue

        name = entry.get("name", "?")
        spec = entry.get("spec")

        if spec is None:
            problems.append(
                f"{name}: source=local_yaml なのに spec が null"
                "（YAML ファイルが存在するか確認し索引を再生成スベシ）"
            )
            continue

        spec_path = repo_root / spec
        if not spec_path.exists():
            problems.append(
                f"{name}: spec パス {spec!r} がディスク上に存在しない"
            )

    return not problems, problems


def main() -> int:
    ok1, problems1 = validate_yaml_skills()
    ok2, problems2 = validate_index_consistency()

    all_ok = ok1 and ok2
    all_problems = problems1 + problems2

    if all_ok:
        yaml_count = sum(
            1
            for p in _YAML_DIR.glob("*.yaml")
            if p.name != _SCHEMA_FILENAME
        )
        print(f"skills YAML 構造 OK（{yaml_count} 件）・索引整合 OK")
        return 0

    for p in all_problems:
        print(p)
    return 1


if __name__ == "__main__":
    sys.exit(main())
