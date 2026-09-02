"""スキル索引生成ツール v2。

ローカル YAML スキル（.claude/commands/yaml/*.yaml）・ローカル MD スキル・外部プラグイン
（skills-lock.json）を統合し .claude/skills-index.yaml を生成する。

生成: uv run python scripts/gen_skills_index.py
検証: uv run python scripts/gen_skills_index.py --check

正本:
  local_yaml : .claude/commands/yaml/*.yaml（meta.triggers が正本）
  local_md   : .claude/commands/*.md（description の発動キーワードが正本）
  external   : skills-lock.json（キャッシュ SKILL.md frontmatter から best-effort 補完）

派生物: .claude/skills-index.yaml（手編集禁止）
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
_COMMANDS_DIR = _REPO_ROOT / ".claude" / "commands"
_YAML_DIR = _COMMANDS_DIR / "yaml"
_LOCK_FILE = _REPO_ROOT / "skills-lock.json"
_ARTIFACT = _REPO_ROOT / ".claude" / "skills-index.yaml"
_GENERATOR_VERSION = 2
_SCHEMA_FILENAME = "_schema.yaml"


def _sha256_raw(path: Path) -> str:
    # CRLF → LF 正規化してからハッシュする（Windows checkout の改行差異を吸収）
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _combined_sha256(
    commands_dir: Path,
    yaml_dir: Path | None = None,
    lock_file: Path | None = None,
) -> str:
    """MD + YAML + skills-lock.json の決定論的結合 SHA256。

    ファイル名昇順で計算する。YAML は _schema.yaml を除外する。
    yaml_dir が None または存在しない場合は MD のみで計算する。
    lock_file が None の場合は _LOCK_FILE をデフォルトとして使用する。
    """
    parts: dict[str, str] = {}

    for p in sorted(commands_dir.glob("*.md")):
        parts[f"md:{p.name}"] = _sha256_raw(p)

    if yaml_dir is None:
        yaml_dir = commands_dir / "yaml"
    if yaml_dir.exists():
        for p in sorted(yaml_dir.glob("*.yaml")):
            if p.name == _SCHEMA_FILENAME:
                continue
            parts[f"yaml:{p.name}"] = _sha256_raw(p)

    # skills-lock.json を含める: 外部プラグインの追加・削除が --check で検出されるようにする
    if lock_file is None:
        lock_file = _LOCK_FILE
    if lock_file.exists():
        parts["lock:skills-lock.json"] = _sha256_raw(lock_file)

    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()


def _source_mtime_iso(commands_dir: Path, yaml_dir: Path | None = None) -> str:
    """最新 mtime を ISO 8601 UTC で返す（冪等性保証）。"""
    mtimes: list[float] = [
        os.path.getmtime(p) for p in commands_dir.glob("*.md")
    ]
    if yaml_dir is None:
        yaml_dir = commands_dir / "yaml"
    if yaml_dir.exists():
        mtimes.extend(
            os.path.getmtime(p)
            for p in yaml_dir.glob("*.yaml")
            if p.name != _SCHEMA_FILENAME
        )
    latest = max(mtimes, default=0.0)
    return datetime.datetime.fromtimestamp(latest, tz=datetime.UTC).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _parse_front_matter(text: str) -> dict:
    """YAML front matter をパースして辞書を返す。なければ {} を返す。"""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    block = text[3:end].strip()
    try:
        return yaml.safe_load(block) or {}
    except yaml.YAMLError:
        return {}


def _parse_keywords(description: str) -> list[str]:
    """発動キーワードを抽出する。

    日本語「X」パターンを優先する。なければ英語 "X" パターンを適用する。
    """
    ja_kw = re.findall(r"「([^」]+)」", description)
    if ja_kw:
        return ja_kw
    return re.findall(r'"([^"]+)"', description)


def _load_skill_yaml(path: Path) -> dict | None:
    """スキル YAML を読み込む。meta フィールドがなければ None を返す。"""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError):
        return None
    if not isinstance(data.get("meta"), dict):
        return None
    return data


def _load_external_skills(lock_file: Path) -> list[dict]:
    """skills-lock.json から外部スキル情報を取得する。

    キャッシュ内の SKILL.md frontmatter から triggers を補完する（best-effort）。
    取得できない場合は triggers を空リストとする。
    """
    if not lock_file.exists():
        return []

    try:
        lock = json.loads(lock_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    plugin_cache = Path.home() / ".claude" / "plugins" / "cache"
    # skills-lock.json 由来の文字列をパス構築に使う前に検証するパターン
    _SAFE_PATH_COMPONENT = re.compile(r'^[A-Za-z0-9_.\-]+$')
    result: list[dict] = []

    for skill_name, info in sorted(lock.get("skills", {}).items()):
        source = info.get("source", "")
        skill_path = info.get("skillPath", "")
        triggers: list[str] = []

        if plugin_cache.exists() and source and skill_path:
            source_parts = source.split("/")
            if len(source_parts) == 2:
                org, repo = source_parts
                # org/repo はアルファベット・数字・_.-のみ許可（path traversal 防止）
                if not (_SAFE_PATH_COMPONENT.fullmatch(org) and _SAFE_PATH_COMPONENT.fullmatch(repo)):
                    continue
                cache_base = plugin_cache / org / repo
                if cache_base.exists():
                    # バージョンディレクトリを mtime 降順で探す（semver は文字列ソート不可）
                    try:
                        version_dirs = sorted(
                            cache_base.iterdir(),
                            key=lambda p: p.stat().st_mtime,
                            reverse=True,
                        )
                    except OSError:
                        version_dirs = []
                    for version_dir in version_dirs:
                        candidate = version_dir / skill_path
                        # resolve() で symlink 等の迂回を含む実パスを確認し、
                        # plugin_cache の外に出る path traversal を防ぐ。
                        # str.startswith() はパス区切り文字を無視するため使用しない
                        # （例: /cache-evil が /cache の startswith を通り抜ける）。
                        # Path.relative_to() はパス要素単位で包含を検証する。
                        try:
                            resolved = candidate.resolve()
                            cache_root = plugin_cache.resolve()
                            resolved.relative_to(cache_root)  # ValueError で抜ける
                        except (OSError, ValueError):
                            continue
                        if resolved.exists():
                            try:
                                text = resolved.read_text(encoding="utf-8", errors="ignore")
                                fm = _parse_front_matter(text)
                                desc = (fm.get("description") or "").strip()
                                triggers = _parse_keywords(desc)
                            except OSError:
                                pass
                            break

        result.append({
            "name": skill_name,
            "source": "external",
            "source_repo": source,
            "operational": None,
            "spec": None,
            "triggers": triggers,
            "tags": [],
            "priority": "normal",
        })

    return result


def build(
    commands_dir: Path,
    yaml_dir: Path | None = None,
    lock_file: Path | None = None,
) -> dict:
    """スキル情報を統合して索引辞書を返す。"""
    if yaml_dir is None:
        yaml_dir = commands_dir / "yaml"
    if lock_file is None:
        lock_file = _LOCK_FILE

    skills: list[dict] = []

    # YAML 変換済みスキルの stem セット（pairing key はファイル名 stem）
    yaml_stems: set[str] = set()
    if yaml_dir.exists():
        for p in yaml_dir.glob("*.yaml"):
            if p.name != _SCHEMA_FILENAME:
                yaml_stems.add(p.stem)

    # ローカル YAML スキル
    if yaml_dir.exists():
        for p in sorted(yaml_dir.glob("*.yaml")):
            if p.name == _SCHEMA_FILENAME:
                continue
            data = _load_skill_yaml(p)
            if data is None:
                continue
            meta = data["meta"]
            skills.append({
                "name": meta.get("name") or p.stem,
                "source": "local_yaml",
                "operational": f".claude/commands/{p.stem}.md",
                "spec": f".claude/commands/yaml/{p.name}",
                "triggers": meta.get("triggers") or [],
                "tags": meta.get("tags") or [],
                "priority": meta.get("priority") or "normal",
            })

    # ローカル MD スキル（YAML 未変換のもの）
    for md_path in sorted(commands_dir.glob("*.md")):
        if md_path.stem in yaml_stems:
            continue
        text = md_path.read_text(encoding="utf-8")
        fm = _parse_front_matter(text)
        description = (fm.get("description") or "").strip()
        skills.append({
            "name": fm.get("name") or md_path.stem,
            "source": "local_md",
            "operational": f".claude/commands/{md_path.name}",
            "spec": None,
            "triggers": _parse_keywords(description),
            "tags": [],
            "priority": "normal",
        })

    # 外部プラグイン
    skills.extend(_load_external_skills(lock_file))

    return {
        "meta": {
            "generated_at": _source_mtime_iso(commands_dir, yaml_dir),
            "generator_version": _GENERATOR_VERSION,
            "source_sha256": _combined_sha256(commands_dir, yaml_dir, lock_file),
            "sources": {
                "local_yaml_glob": ".claude/commands/yaml/*.yaml",
                "local_md_glob": ".claude/commands/*.md",
                "external_lock": "skills-lock.json",
            },
        },
        "skills": skills,
    }


def verify_sync(
    source_dir: str | Path,
    artifact: str | Path,
    yaml_dir: str | Path | None = None,
    lock_file: str | Path | None = None,
) -> tuple[bool, str]:
    """生成物の source_sha256 と現スキル群の結合 SHA256 を照合する。

    source_dir : .claude/commands/（MD スキルのディレクトリ）
    artifact   : .claude/skills-index.yaml
    yaml_dir   : .claude/commands/yaml/（省略時は source_dir/yaml）
    lock_file  : skills-lock.json（省略時は _LOCK_FILE）
    """
    commands_dir = Path(source_dir)
    artifact = Path(artifact)
    yaml_dir = Path(yaml_dir) if yaml_dir else commands_dir / "yaml"
    lock_file_path = Path(lock_file) if lock_file else None

    if not commands_dir.exists():
        return True, f"(commands_dir {commands_dir} missing — skipped)"
    if not artifact.exists():
        return True, f"(artifact {artifact} not yet generated — skipped)"
    try:
        obj = yaml.safe_load(artifact.read_text(encoding="utf-8")) or {}
    except Exception as e:
        return False, f"artifact parse error: {e}"

    recorded = (obj.get("meta") or {}).get("source_sha256")
    current = _combined_sha256(commands_dir, yaml_dir, lock_file_path)

    if recorded == current:
        return True, "[skills-index] 同期 OK"
    return False, (
        "skills-index.yaml <-> スキルファイル群 不一致\n"
        f"  recorded: {recorded}\n"
        f"  current:  {current}\n"
        "  再生成: uv run python scripts/gen_skills_index.py"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="スキル索引生成 v2")
    parser.add_argument("--check", action="store_true", help="同期検証のみ（生成しない）")
    parser.add_argument("--source-dir", default=str(_COMMANDS_DIR))
    parser.add_argument("--yaml-dir", default=str(_YAML_DIR))
    parser.add_argument("--lock-file", default=str(_LOCK_FILE))
    parser.add_argument("--out", default=str(_ARTIFACT))
    args = parser.parse_args()

    commands_dir = Path(args.source_dir)
    yaml_dir = Path(args.yaml_dir)
    lock_file = Path(args.lock_file)
    out = Path(args.out)

    if args.check:
        ok, msg = verify_sync(commands_dir, out, yaml_dir)
        print(msg)
        return 0 if ok else 1

    data = build(commands_dir, yaml_dir, lock_file)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        yaml.dump(
            data,
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )
    print(f"生成完了: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
