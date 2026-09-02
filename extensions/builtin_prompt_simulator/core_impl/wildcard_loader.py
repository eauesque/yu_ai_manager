"""Manage wildcard file writes, lookups, deletions, and renames."""

import re
from pathlib import Path

# Re-export parse/load functions for backward compatibility
from .wildcard_parser import load_wildcards_from_dirs, load_wildcards_from_zip

__all__ = [
    "load_wildcards_from_dirs",
    "load_wildcards_from_zip",
    "save_wildcard_file",
    "find_wildcard_files",
    "delete_wildcard_files",
    "rename_wildcard_files",
    "validate_dirs",
]


# Reserved/dangerous characters for wildcard names
# (Windows-forbidden + control chars; '/' is allowed as separator)
_WC_NAME_BAD_CHARS = re.compile(r'[<>:"|?*\x00-\x1f\\]')


def _sanitize_wildcard_name(name: object) -> str | None:
    """Validate a wildcard name and return a clean POSIX-style relative path.

    Returns ``None`` if the name is invalid (absolute, traversal, reserved
    chars, empty parts, etc.). Backslashes are normalised to forward slashes
    before validation.
    """
    if not isinstance(name, str):
        return None
    cleaned = name.strip().replace("\\", "/")
    if not cleaned or cleaned.startswith("/") or cleaned.startswith("."):
        return None
    parts = cleaned.split("/")
    for p in parts:
        if not p or p in (".", ".."):
            return None
        if _WC_NAME_BAD_CHARS.search(p):
            return None
        # Windows quirks: trailing dot/space is unsafe
        if p.endswith(".") or p.endswith(" "):
            return None
    return "/".join(parts)


def _detect_newline(path: Path) -> str:
    """Inspect the first 8 KiB of a file and return its dominant newline style."""
    try:
        with open(path, "rb") as f:
            sample = f.read(8192)
    except OSError:
        return "\n"
    return "\r\n" if b"\r\n" in sample else "\n"


def _is_within(child: Path, parent: Path) -> bool:
    """Return True if ``child`` resolves underneath ``parent`` (containment check)."""
    try:
        child_resolved = child.resolve()
        parent_resolved = parent.resolve()
    except OSError:
        return False
    try:
        child_resolved.relative_to(parent_resolved)
    except ValueError:
        return False
    return True


def save_wildcard_file(name: str, lines: list[str], dirs: list[str]) -> str:
    """Write wildcard ``lines`` to ``<dir>/<name>.txt`` and return the absolute path.

    Lookup order:
    1. Scan ``dirs`` (in order) for an existing ``<dir>/<name>.txt`` and overwrite it,
       preserving the file's existing newline style.
    2. If no existing file is found, create a new one inside the **first** directory
       in ``dirs`` (creating any missing parent directories) using LF newlines.

    Raises:
        ValueError: if ``name`` is invalid, ``dirs`` is empty, the resolved path
            escapes its base directory, or the first dir does not exist when a
            new file must be created.
    """
    if not dirs:
        raise ValueError("No wildcard directories configured")

    sanitized = _sanitize_wildcard_name(name)
    if sanitized is None:
        raise ValueError(f"Invalid wildcard name: {name!r}")

    rel_parts = sanitized.split("/")
    rel_filename = rel_parts[-1] + ".txt"
    rel_subdirs = rel_parts[:-1]

    target: Path | None = None
    newline = "\n"

    # 1. Look for an existing file in any configured directory
    for d in dirs:
        if not isinstance(d, str) or not d.strip():
            continue
        base = Path(d.strip())
        if not base.is_dir():
            continue
        candidate = base.joinpath(*rel_subdirs, rel_filename)
        if not _is_within(candidate, base):
            continue
        if candidate.is_file():
            target = candidate
            newline = _detect_newline(candidate)
            break

    # 2. Otherwise create a new file in the first valid directory
    if target is None:
        first = Path(dirs[0].strip()) if isinstance(dirs[0], str) else None
        if first is None or not first.is_dir():
            raise ValueError(
                f"First wildcard directory does not exist: {dirs[0]!r}"
            )
        candidate = first.joinpath(*rel_subdirs, rel_filename)
        # Verify containment before creating any directories to prevent
        # an escaped path from causing unintended mkdir side-effects.
        if not _is_within(candidate, first):
            raise ValueError("Resolved wildcard path escapes its base directory")
        candidate.parent.mkdir(parents=True, exist_ok=True)
        target = candidate

    # Normalise lines: strip any trailing CR/LF the client may have sent,
    # then join with the chosen newline. Always end with a trailing newline
    # if there is any content (POSIX convention, friendlier to diff tools).
    cleaned_lines = [str(line).rstrip("\r\n") for line in lines]
    text = newline.join(cleaned_lines)
    if text and not text.endswith(newline):
        text += newline

    # ``newline=""`` keeps the bytes we wrote verbatim instead of letting
    # Python translate "\n" → os.linesep on Windows.
    target.write_text(text, encoding="utf-8", newline="")
    return str(target.resolve())


def find_wildcard_files(name: str, dirs: list[str]) -> list[Path]:
    """Return all existing ``<dir>/<name>.txt`` matches across configured dirs.

    Multiple matches are possible because configuration may include several
    directories that happen to contain a file with the same wildcard name. The
    loader's "later overrides earlier" rule means only the last one is visible
    to consumers, but we still return every match so destructive operations
    (delete / rename) can act on all of them and avoid resurrecting shadowed
    copies later.
    """
    sanitized = _sanitize_wildcard_name(name)
    if sanitized is None:
        raise ValueError(f"Invalid wildcard name: {name!r}")
    rel_parts = sanitized.split("/")
    rel_filename = rel_parts[-1] + ".txt"
    rel_subdirs = rel_parts[:-1]
    matches: list[Path] = []
    for d in dirs:
        if not isinstance(d, str) or not d.strip():
            continue
        base = Path(d.strip())
        if not base.is_dir():
            continue
        candidate = base.joinpath(*rel_subdirs, rel_filename)
        if not _is_within(candidate, base):
            continue
        if candidate.is_file():
            matches.append(candidate)
    return matches


def delete_wildcard_files(name: str, dirs: list[str]) -> list[str]:
    """Delete every ``<dir>/<name>.txt`` match. Returns absolute paths removed.

    Raises:
        ValueError: invalid name or no matches found.
        OSError: filesystem errors during unlink.
    """
    matches = find_wildcard_files(name, dirs)
    if not matches:
        raise ValueError(f"Wildcard not found on disk: {name!r}")
    removed: list[str] = []
    for path in matches:
        resolved = str(path.resolve())
        path.unlink()
        removed.append(resolved)
    return removed


def rename_wildcard_files(old_name: str, new_name: str, dirs: list[str]) -> list[dict]:
    """Rename every on-disk match of ``old_name`` to ``new_name`` (in place).

    "In place" means the file stays inside the directory it was found in;
    only the relative path within that directory changes. This avoids
    surprise moves between configured directories with different priorities.

    Collision check: if any ``<dir>/<new_name>.txt`` already exists in any
    configured directory, the operation is aborted before touching disk.

    Returns a list of ``{"from": "...", "to": "..."}`` entries.

    Raises:
        ValueError: invalid name, no matches, or destination collision.
        OSError: filesystem errors during rename.
    """
    if _sanitize_wildcard_name(new_name) is None:
        raise ValueError(f"Invalid wildcard name: {new_name!r}")

    matches = find_wildcard_files(old_name, dirs)
    if not matches:
        raise ValueError(f"Wildcard not found on disk: {old_name!r}")

    if find_wildcard_files(new_name, dirs):
        raise ValueError(
            f"Destination wildcard already exists: {new_name!r}"
        )

    sanitized_new = _sanitize_wildcard_name(new_name)
    new_parts = sanitized_new.split("/")
    new_filename = new_parts[-1] + ".txt"
    new_subdirs = new_parts[:-1]

    # Build the planned destination for each match and pre-validate containment.
    plans: list[tuple[Path, Path]] = []
    for src in matches:
        # Determine which configured base ``src`` belongs to (the first one
        # that contains it). We need this to anchor the new path inside the
        # same base directory.
        base: Path | None = None
        for d in dirs:
            if not isinstance(d, str) or not d.strip():
                continue
            candidate_base = Path(d.strip())
            if not candidate_base.is_dir():
                continue
            try:
                src.resolve().relative_to(candidate_base.resolve())
                base = candidate_base
                break
            except (OSError, ValueError):
                continue
        if base is None:
            raise ValueError(f"Could not locate base directory for {src}")
        dst = base.joinpath(*new_subdirs, new_filename)
        if not _is_within(dst, base):
            raise ValueError("Resolved wildcard path escapes its base directory")
        if dst.exists():
            # Defensive: even though find_wildcard_files() returned no matches
            # for the new name, a non-.txt sibling could still collide.
            raise ValueError(f"Destination path already exists: {dst}")
        plans.append((src, dst))

    results: list[dict] = []
    for src, dst in plans:
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        results.append({"from": str(src.resolve()), "to": str(dst.resolve())})
    return results


def validate_dirs(dirs: list[str]) -> list[dict]:
    """Check each directory path and return validation results."""
    results = []
    for d in dirs:
        p = Path(d)
        results.append({
            "path": d,
            "exists": p.is_dir(),
        })
    return results
