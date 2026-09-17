"""CHANGELOG.md is canonical; CHANGELOG.ja.md must not carry versions it lacks.

`CHANGELOG.md` is the canonical engineering changelog and `CHANGELOG.ja.md` is
the release-facing one, so every version documented in the release file must
also exist in the canonical file. That held until it silently stopped:

* v4.711.1, .2 and .3 (2026-09-09) were released -- VERSION said `4.711.3` --
  with their entries written ONLY into `CHANGELOG.ja.md`. The canonical file's
  newest entry was still 4.711.0, so three shipped fixes (bridge path
  normalization, migration 89, and its rewrite) were absent from the file the
  project treats as the record. It surfaced by accident, while resolving an
  unrelated merge conflict.
* the same thing had already happened twice before, unnoticed: 4.670.1/.2 and
  4.679.3/.4/.5.

Nothing checked either file, so nothing failed. Two rules make it mechanical:

1. the version in `VERSION` must have an entry in `CHANGELOG.md` -- the live
   guard, which fires on the release that forgets the canonical file rather
   than months later;
2. every version in `CHANGELOG.ja.md` must exist in `CHANGELOG.md`, except a
   frozen baseline of the five legacy versions above. The baseline may only
   shrink: paying one off removes it, and a new omission cannot hide inside it.

The reverse direction is deliberately NOT checked. `.ja` is a release subset,
so a version present only in the canonical file is normal, not a defect.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CANONICAL = _REPO_ROOT / "CHANGELOG.md"
_RELEASE = _REPO_ROOT / "CHANGELOG.ja.md"
_VERSION = _REPO_ROOT / "VERSION"

_HEADING = re.compile(r"^## \[([0-9]+(?:\.[0-9]+)*)\]", re.MULTILINE)

# Versions released before this gate existed whose entries never reached the
# canonical file. Frozen: this list may only shrink.
_LEGACY_MISSING = frozenset(
    {"4.670.1", "4.670.2", "4.679.3", "4.679.4", "4.679.5"}
)


def _versions(text: str) -> set[str]:
    return set(_HEADING.findall(text))


def validate(
    canonical: str, release: str, current_version: str
) -> list[str]:
    """Return human-readable problems; empty means the push may proceed."""
    problems: list[str] = []
    documented = _versions(canonical)

    current_version = current_version.strip()
    if current_version and current_version not in documented:
        problems.append(
            f"VERSION says {current_version} but CHANGELOG.md has no "
            f"'## [{current_version}]' entry -- the canonical changelog is the "
            f"record, so a released version missing from it is missing, "
            f"whether or not CHANGELOG.ja.md describes it"
        )

    missing = _versions(release) - documented - _LEGACY_MISSING
    for version in sorted(missing):
        problems.append(
            f"{version} is documented in CHANGELOG.ja.md but absent from "
            f"CHANGELOG.md (canonical). Copy the entry across; do not add it "
            f"to the legacy baseline"
        )

    paid_off = _LEGACY_MISSING & documented
    if paid_off:
        problems.append(
            "the legacy baseline in this script lists version(s) that now DO "
            f"appear in CHANGELOG.md: {', '.join(sorted(paid_off))}. Remove "
            f"them from _LEGACY_MISSING -- a baseline that outlives its "
            f"omissions stops being a ratchet"
        )
    return problems


def _self_check() -> None:
    """Replay the omissions that motivated this gate."""
    canonical = "## [4.712.0]\nx\n\n## [4.711.0]\ny\n"

    # 1. The live guard: VERSION released past the canonical changelog.
    assert validate(canonical, "", "4.711.3"), "a released-but-undocumented version must fail"

    # 2. The historical drift: entries that only ever reached the release file.
    release = "## [4.711.3]\na\n\n## [4.711.2]\nb\n\n## [4.711.1]\nc\n"
    problems = validate(canonical, release, "4.712.0")
    assert len(problems) == 3, problems

    # 3. The legacy baseline is exempt -- but only while it is still missing.
    legacy = "## [4.670.1]\na\n\n## [4.679.3]\nb\n"
    assert not validate(canonical, legacy, "4.712.0"), "baseline must stay exempt"
    assert validate(
        canonical + "\n## [4.670.1]\nz\n", legacy, "4.712.0"
    ), "a baseline entry that got backfilled must be removed from the baseline"

    # 4. `.ja` being a subset is normal: the canonical file having more is fine.
    assert not validate(canonical, "## [4.711.0]\ny\n", "4.712.0"), (
        "a version only in the canonical file is expected, not a defect"
    )


def main() -> int:
    _self_check()
    problems = validate(
        _CANONICAL.read_text(encoding="utf-8"),
        _RELEASE.read_text(encoding="utf-8"),
        _VERSION.read_text(encoding="utf-8"),
    )
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
