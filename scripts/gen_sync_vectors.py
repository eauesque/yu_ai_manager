#!/usr/bin/env python3
"""Generate deterministic LAN Cowork sync vectors for the Rust pure layer."""
from __future__ import annotations

import json
import pathlib as _pathlib
import sys as _sys

_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
from lan_cowork_repo import vectors_dir  # noqa: E402


def entry(hash_: str, mtime: float, size: int = 1) -> dict[str, object]:
    return {"hash": hash_, "mtime": mtime, "size": size}


def main() -> None:
    vectors = {
        "diff_cases": [
            {"label": "remote_only_fetch", "local": {}, "remote": {"remote.txt": entry("a", 1.0)}, "fetch": ["remote.txt"], "push": []},
            {"label": "local_only_push", "local": {"local.txt": entry("a", 1.0)}, "remote": {}, "fetch": [], "push": ["local.txt"]},
            {"label": "same_hash_no_action", "local": {"same.txt": entry("a", 1.0)}, "remote": {"same.txt": entry("a", 2.0, 2)}, "fetch": [], "push": []},
            {"label": "newer_remote_fetch", "local": {"changed.txt": entry("a", 1.0)}, "remote": {"changed.txt": entry("b", 2.0)}, "fetch": ["changed.txt"], "push": []},
            {"label": "equal_mtime_push", "local": {"changed.txt": entry("a", 2.0)}, "remote": {"changed.txt": entry("b", 2.0)}, "fetch": [], "push": ["changed.txt"]},
        ],
        "backup_names": [
            {"source": "a.txt", "backup": "a.txt.bak"},
            {"source": "a", "backup": "a.bak"},
            {"source": "a.tar.gz", "backup": "a.tar.gz.bak"},
            {"source": ".bashrc", "backup": ".bashrc.bak"},
            {"source": "a.", "backup": "a..bak"},
        ],
        "path_cases": [
            {"label": "normal", "path": "nested/file.txt", "valid": True},
            {"label": "deep_missing", "path": "missing/deep/file.txt", "valid": True},
            {"label": "converges_inside_root", "path": "nonexistent/../ok.txt", "valid": True},
            {"label": "parent_escape", "path": "../outside.txt", "valid": False},
            {"label": "multiple_parent_escape", "path": "a/../../..", "valid": False},
            {"label": "absolute", "path": "/tmp/outside.txt", "valid": False},
            {"label": "nul", "path": "bad\0path", "valid": False},
        ],
    }
    output = vectors_dir() / "sync_vectors.json"
    output.write_text(json.dumps(vectors, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {output}")


if __name__ == "__main__":
    main()
