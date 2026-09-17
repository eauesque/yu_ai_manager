"""TODO.md must not keep entries that are already finished.

Twice now a settled conclusion sat in TODO.md long enough to mislead someone:

* the ruff ratchet item kept the title "返済スベシ (759 件)" after all ten rules
  had been examined and `S110` paid off, dragging an 8,700-character history
  behind it. On 2026-09-08 it was picked up as actionable debt -- the real work
  remaining was zero.
* eleven `done(...)` entries were sitting in TODO.md with the completion marker
  already written. A reader follows the whole body before reaching "done".

TODO.md's own header says finished items move to
`docs/development/archives/todo-completed-YYYY-MM.md`. This check makes that
mechanical: a `done(...)` entry in TODO.md fails the push.

`note`/`decided` are NOT flagged. The header keeps them deliberately, but only
while a live `todo` reads them, and no checker can judge that -- a human must.
This gate covers the unambiguous half.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TODO = _REPO_ROOT / "TODO.md"

# Top-level entry headers only: `- done(scope, version) **...` at column 0.
#
# Indented `  - done(...)` bullets are NOT entries. They mark which parts of a
# still-open parent are settled, and the parent reads wrong without them --
# `note(rust/auto_stubs)` is exactly that shape, listing repaid stubs beside
# ones still waiting on an authorization decision. The first draft of this gate
# flagged them, and its self-check asserted that it should; both were wrong.
_DONE_ENTRY = re.compile(r"^-\s+done\(")


def find_done_entries(text: str) -> list[tuple[int, str]]:
    """Return (line number, first 90 chars) for each top-level `done(...)` entry."""
    found: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if _DONE_ENTRY.match(line):
            found.append((number, line.strip()[:90]))
    return found


def validate(todo_path: Path = _TODO) -> tuple[bool, list[str]]:
    if not todo_path.exists():
        return True, []
    entries = find_done_entries(todo_path.read_text(encoding="utf-8"))
    if not entries:
        return True, []
    problems = [f"  TODO.md:{number}  {text}" for number, text in entries]
    return False, problems


def _self_check() -> list[str]:
    """Replay what this gate exists to catch, and what it must leave alone."""
    failures: list[str] = []

    caught = find_done_entries("- done(parity, v4.698.0) **something finished.**\n")
    if len(caught) != 1:
        failures.append("a top-level `- done(...)` entry was not caught")

    # The correction above, pinned: a settled sub-point inside a live parent is
    # context, not a stranded entry. Flagging it would force deleting text the
    # parent depends on.
    nested = find_done_entries(
        "- note(rust/auto_stubs) **stubs, some repaid.**\n"
        "  - done(rust/backup, v4.696.0) この二件ハ返済済ミ。\n"
        "  - `gateway_backends_list` ハ認可ノ決着ヲ要ス。\n"
    )
    if nested:
        failures.append("flagged a `done` sub-bullet inside a live parent entry")

    # Prose mentioning the word must stay silent, or the gate becomes noise
    # nobody can satisfy.
    for benign in (
        "- todo(rust) **これは done ではない。** 本文中の語ナリ。\n",
        "- note(parity) done を語ル註釈。\n",
        "> 完了シタル項ハ archive ヘ移スベシ（done ヲ TODO ニ残スナ）。\n",
    ):
        if find_done_entries(benign):
            failures.append(f"false positive on prose: {benign.strip()[:50]}")

    return failures


def main() -> int:
    broken = _self_check()
    if broken:
        print("検出器自身ガ壊レ居ル:")
        for line in broken:
            print(f"  {line}")
        return 1

    ok, problems = validate()
    if ok:
        return 0
    print("TODO.md ニ `done(...)` ノ項ガ残リ居ル:")
    for problem in problems:
        print(problem)
    print(
        "\n完了シタル項ハ其ノ都度 docs/development/archives/todo-completed-YYYY-MM.md ヘ\n"
        "移スベシ。残シ置ケバ次ニ読ム者ガ「未着手ノ債務」ト読ミ違フ。\n"
        "移ス時ハ「何ヲ以テ決着ト判ジタルカ」ヲ必ズ添ヘヨ。"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
