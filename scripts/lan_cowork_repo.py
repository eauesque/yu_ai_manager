"""Where the LAN Cowork wire-format vectors live, now that the crate is gone.

The generators here run the *Python* implementation and write golden vectors
that the Rust crate's unit tests read with `include_str!`. They used to write
into `crates/lan-cowork/tests/vectors/`; that crate now lives in its own
repository (mirrored to `eauesque/yu-lan-cowork`), so
the output has to cross a repo boundary.

Resolution order:

1. `$YU_LAN_COWORK` — an explicit checkout path.
2. `../yu-lan-cowork` next to this checkout — the layout the mirror's own
   `sync-from-yu-ai-manager.sh` assumes.

Generating a vector is only half the job: the crate has to be rebuilt and its
tests run in *that* repo, and the change has to reach the public mirror before
`crates/Cargo.toml` can pin it. `vectors_dir()` raises rather than silently
writing into a scratch directory, because a vector nobody consumes looks exactly
like a vector that passed.
"""

from __future__ import annotations

import os
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent


def _main_checkout() -> pathlib.Path:
    """The checkout that owns this script, resolving through git worktrees.

    Inside `.claude/worktrees/<name>` the repo root is three levels below the
    directory holding the sibling checkouts, so `REPO.parent` points at the
    worktrees directory and the sibling is never found. The mirror-drift gate
    had the same defect; it surfaced there as a check that silently skipped, and
    here as a generator that refuses to run.
    """
    if REPO.parent.name == "worktrees":
        return REPO.parent.parent.parent
    return REPO


def lan_cowork_checkout() -> pathlib.Path:
    """Return the yu-lan-cowork checkout, or raise with what to do about it.

    An explicit `$YU_LAN_COWORK` is authoritative: if it is set and wrong, that
    is an error, not a reason to look elsewhere. Falling through to the sibling
    checkout answers a question nobody asked — the caller named a path — and it
    hides the typo behind a result that looks right. The mutation check caught
    exactly that: pointing the variable at a nonexistent directory still
    resolved to the real checkout, so a gate meant to run *without* one never
    did, and its no-checkout branch went unproven.
    """
    override = os.environ.get("YU_LAN_COWORK")
    if override:
        path = pathlib.Path(override)
        if (path / "Cargo.toml").is_file():
            return path
        raise SystemExit(
            f"$YU_LAN_COWORK={override} is not a yu-lan-cowork checkout "
            "(no Cargo.toml there). Unset it to fall back to ../yu-lan-cowork."
        )

    sibling = _main_checkout().parent / "yu-lan-cowork"
    if (sibling / "Cargo.toml").is_file():
        return sibling

    raise SystemExit(
        f"LAN Cowork checkout not found (tried: {sibling}).\n"
        "The crate moved to its own repository; vectors must be written there.\n"
        "  git clone https://github.com/eauesque/yu-lan-cowork\n"
        "  YU_LAN_COWORK=/path/to/yu-lan-cowork uv run python scripts/lan_cowork_repo.py"
    )


def vectors_dir() -> pathlib.Path:
    """Return `<checkout>/tests/vectors`, creating it if the checkout exists."""
    out = lan_cowork_checkout() / "tests" / "vectors"
    out.mkdir(parents=True, exist_ok=True)
    return out
