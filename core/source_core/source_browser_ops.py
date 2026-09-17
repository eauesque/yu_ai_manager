"""Source browser public API -- tree, read, search operations.

MCP / API endpoints call these functions to browse project source code
with security restrictions applied.
"""

from __future__ import annotations

import fnmatch
import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .source_browser_security import (
    ALLOWED_EXTENSIONLESS,
    ALLOWED_EXTENSIONS,
    BLOCKED_DIRS,
    MAX_FILE_SIZE_BYTES,
    MAX_LINES,
    MAX_SEARCH_RESULTS,
    MAX_TREE_DEPTH,
    _get_project_root,
    _is_dir_blocked,
    _is_file_allowed,
    _resolve_safe,
)

logger = logging.getLogger(__name__)

# ── Public API ────────────────────────────────

def source_tree(
    rel_path: str = "",
    depth: int = 3,
) -> dict[str, Any]:
    """Return a directory tree listing."""
    depth = max(1, min(depth, MAX_TREE_DEPTH))
    target, err = _resolve_safe(rel_path)
    if err:
        return {"ok": False, "error": err}
    if not target.is_dir():
        return {"ok": False, "error": f"ディレクトリが見つかりません: {rel_path}"}

    root = _get_project_root()

    def _is_inside_root(path: Path) -> bool:
        try:
            path.resolve().relative_to(root)
            return True
        except (OSError, ValueError):
            return False

    def _walk(dirpath: Path, current_depth: int) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        try:
            items = sorted(dirpath.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            return entries

        for item in items:
            name = item.name
            if item.is_symlink() or not _is_inside_root(item):
                continue

            if item.is_dir():
                if _is_dir_blocked(name):
                    continue
                node: dict[str, Any] = {
                    "name": name,
                    "type": "dir",
                    "path": str(item.relative_to(root)).replace("\\", "/"),
                }
                if current_depth < depth:
                    node["children"] = _walk(item, current_depth + 1)
                entries.append(node)
            else:
                if not _is_file_allowed(item):
                    continue
                entries.append({
                    "name": name,
                    "type": "file",
                    "path": str(item.relative_to(root)).replace("\\", "/"),
                    "size": item.stat().st_size,
                })
        return entries

    tree = _walk(target, 1)
    return {
        "ok": True,
        "root": str(target.relative_to(root)).replace("\\", "/") or ".",
        "depth": depth,
        "entries": tree,
    }


def source_read(
    rel_path: str,
    offset: int = 0,
    limit: int = MAX_LINES,
) -> dict[str, Any]:
    """Return file contents with line numbers."""
    if not rel_path:
        return {"ok": False, "error": "ファイルパスを指定してください"}

    target, err = _resolve_safe(rel_path)
    if err:
        return {"ok": False, "error": err}
    # Reject symlinks even if they point inside the project root: they can be
    # used to bypass the BLOCKED_PATTERNS allow-list (e.g. ``link.py -> .env``).
    # source_tree / source_search already filter symlinks out of their
    # results, so legitimate clients never reach here with a symlink path.
    # Note: must check the literal path, not ``target`` (which is already
    # resolved by _resolve_safe).
    literal = (_get_project_root() / rel_path.lstrip("/\\").replace("\\", "/"))
    if literal.is_symlink():
        return {"ok": False, "error": "シンボリックリンクへのアクセスは禁止されています"}
    if not target.is_file():
        return {"ok": False, "error": f"ファイルが見つかりません: {rel_path}"}
    if not _is_file_allowed(target):
        return {"ok": False, "error": "このファイルは読み取り対象外です"}

    # Size check
    size = target.stat().st_size
    if size > MAX_FILE_SIZE_BYTES:
        return {
            "ok": False,
            "error": f"ファイルサイズが上限を超えています ({size:,} bytes > {MAX_FILE_SIZE_BYTES:,} bytes)",
        }

    offset = max(0, offset)
    limit = max(1, min(limit, MAX_LINES))
    selected: list[str] = []
    try:
        with target.open("r", encoding="utf-8", errors="replace") as fh:
            total_lines = 0
            end = offset + limit
            for total_lines, line in enumerate(fh, 1):
                idx = total_lines - 1
                if offset <= idx < end:
                    selected.append(line.rstrip("\n\r"))
    except Exception as e:
        return {"ok": False, "error": f"読み取りエラー: {e}"}

    root = _get_project_root()
    return {
        "ok": True,
        "path": str(target.relative_to(root)).replace("\\", "/"),
        "total_lines": total_lines,
        "offset": offset,
        "limit": limit,
        "content": "\n".join(
            f"{offset + i + 1:>5}\t{line}" for i, line in enumerate(selected)
        ),
    }


def source_search(
    query: str,
    glob_pattern: str = "",
    max_results: int = 30,
) -> dict[str, Any]:
    """Search source code for text (grep equivalent)."""
    if not query or len(query) < 2:
        return {"ok": False, "error": "検索クエリは 2 文字以上必要です"}

    max_results = max(1, min(max_results, MAX_SEARCH_RESULTS))
    root = _get_project_root()

    results = _search_with_rg(root, query, glob_pattern, max_results)
    if results is None:
        results = _search_with_python(root, query, glob_pattern, max_results)

    return {
        "ok": True,
        "query": query,
        "glob": glob_pattern or "*",
        "total": len(results),
        "results": results,
    }


def _search_with_python(
    root: Path,
    query: str,
    glob_pattern: str,
    max_results: int,
) -> list[dict[str, Any]]:
    """Python-based text search fallback."""
    results: list[dict[str, Any]] = []
    pattern = re.compile(re.escape(query), re.IGNORECASE)

    for dirpath_str, dirnames, filenames in os.walk(root):
        dirpath = Path(dirpath_str)

        # Skip blocked directories (in-place removal propagates to os.walk)
        dirnames[:] = [
            d for d in dirnames
            if not _is_dir_blocked(d) and not (dirpath / d).is_symlink()
        ]

        for fname in filenames:
            fpath = dirpath / fname
            if fpath.is_symlink():
                continue
            if not _is_file_allowed(fpath):
                continue

            # Glob filter
            if glob_pattern and not fnmatch.fnmatch(fname, glob_pattern):
                continue

            # Size check
            try:
                if fpath.stat().st_size > MAX_FILE_SIZE_BYTES:
                    continue
            except OSError:
                continue

            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                logger.debug("source file unreadable, skipped from the scan: %s", exc)
                continue

            for line_no, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    rel = str(fpath.relative_to(root)).replace("\\", "/")
                    results.append({
                        "file": rel,
                        "line": line_no,
                        "text": line.rstrip()[:200],  # Truncate long lines
                    })
                    if len(results) >= max_results:
                        return results

    return results


def _search_with_rg(
    root: Path,
    query: str,
    glob_pattern: str,
    max_results: int,
) -> list[dict[str, Any]] | None:
    rg = shutil.which("rg")
    if not rg:
        return None

    args = [
        rg,
        "--json",
        "--fixed-strings",
        "--ignore-case",
        "--line-number",
        "--no-heading",
        "--color",
        "never",
    ]
    for ext in sorted(ALLOWED_EXTENSIONS):
        args.extend(["-g", f"*{ext}"])
    for name in sorted(ALLOWED_EXTENSIONLESS):
        args.extend(["-g", name])
    for dirname in sorted(name for name in BLOCKED_DIRS if "*" not in name):
        args.extend(["-g", f"!{dirname}/**"])
    # `--` ends option parsing so the untrusted query can never be smuggled in as
    # an rg flag (e.g. `--pre=<cmd>` would execute an arbitrary preprocessor).
    # --fixed-strings is already set, so a query starting with `-` is searched
    # literally.
    args.extend(["--", query, str(root)])

    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode not in (0, 1):
        return None

    results: list[dict[str, Any]] = []
    for raw in proc.stdout.splitlines():
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "match":
            continue
        data = event.get("data") or {}
        path_text = ((data.get("path") or {}).get("text") or "").strip()
        if not path_text:
            continue
        path = Path(path_text)
        if path.is_symlink() or not _is_file_allowed(path):
            continue
        if glob_pattern and not fnmatch.fnmatch(path.name, glob_pattern):
            continue
        try:
            if path.stat().st_size > MAX_FILE_SIZE_BYTES:
                continue
            rel = str(path.resolve().relative_to(root)).replace("\\", "/")
        except (OSError, ValueError):
            continue
        results.append({
            "file": rel,
            "line": int(data.get("line_number") or 0),
            "text": ((data.get("lines") or {}).get("text") or "").rstrip()[:200],
        })
        if len(results) >= max_results:
            return results
    return results
