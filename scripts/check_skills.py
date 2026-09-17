"""Validate structural health of .claude/skills/*.md files."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from gen_skills_index import _parse_front_matter, _parse_keywords

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SOURCE_DIR = _REPO_ROOT / ".claude" / "commands"
_PATH_TOKEN_RE = re.compile(
    r"(?<![\w./-])"
    r"((?:\.claude|scripts|docs|core|ui|src|tests|extensions|routes|tmp)/"
    r"[A-Za-z0-9._/\-]+\.[A-Za-z0-9]+)"
    r"(?=$|[\s`'\"\])}>。、.,;:])"
)
_PLACEHOLDER_CHARS = frozenset("<{*$")


def _has_front_matter(text: str) -> bool:
    return text.startswith("---") and text.find("\n---", 3) != -1


def _body_after_front_matter(text: str) -> str:
    end = text.find("\n---", 3)
    if end == -1:
        return text
    return text[end + len("\n---") :]


def _extract_repo_paths(text: str) -> list[str]:
    paths: set[str] = set()
    for match in _PATH_TOKEN_RE.finditer(text):
        path = match.group(1)
        if any(char in path for char in _PLACEHOLDER_CHARS):
            continue
        if path.startswith((".claude/data/", "tmp/")):
            continue
        paths.add(path)
    return sorted(paths)


def validate(source_dir: Path) -> tuple[bool, list[str]]:
    """Validate skills and return (ok, human-readable problems)."""
    problems: list[str] = []
    commands: dict[str, list[str]] = {}
    md_paths = sorted(source_dir.glob("*.md"))

    for md_path in md_paths:
        text = md_path.read_text(encoding="utf-8")
        if not _has_front_matter(text):
            problems.append(f"{md_path.name}: front matter 必須")

        fm = _parse_front_matter(text)
        description = fm.get("description")
        if not isinstance(description, str) or not description.strip():
            problems.append(f"{md_path.name}: description 非空必須")
            description_text = ""
        else:
            description_text = description.strip()

        if not _parse_keywords(description_text):
            problems.append(f"{md_path.name}: 索引から発動不能（発動キーワードなし）")

        name = fm.get("name") or md_path.stem
        command = f"/{name}"
        commands.setdefault(command, []).append(md_path.name)

        for path in _extract_repo_paths(_body_after_front_matter(text)):
            if not (_REPO_ROOT / path).exists():
                problems.append(f"{md_path.name}: dangling 参照 `{path}`")

    for command, files in sorted(commands.items()):
        if len(files) > 1:
            joined = ", ".join(files)
            problems.append(f"{command}: コマンド名衝突（{joined}）")

    return not problems, problems


def main() -> int:
    ok, problems = validate(_SOURCE_DIR)
    if ok:
        count = len(list(_SOURCE_DIR.glob("*.md")))
        print(f"skills 構造 OK（{count} 件検査）")
        return 0
    for problem in problems:
        print(problem)
    return 1


if __name__ == "__main__":
    sys.exit(main())
