"""Parse wildcard .txt / .yaml / .yml files from directories or ZIP archives."""

import io
import logging
import os
import zipfile
from pathlib import Path, PurePosixPath

logger = logging.getLogger(__name__)

try:
    import yaml as _yaml
except ImportError:  # PyYAML not installed — skip YAML wildcards gracefully
    _yaml = None

# Maximum total uncompressed size allowed when extracting a ZIP (50 MB)
_ZIP_MAX_UNCOMPRESSED = 50 * 1024 * 1024


def _flatten_yaml(data, prefix: str = "") -> dict[str, list[str]]:
    """Flatten a YAML hierarchy into a wildcard dict {path: [items]}.

    Category keys (dict) become path segments; leaf lists become entries.
    """
    result: dict[str, list[str]] = {}
    if isinstance(data, list):
        items = [str(item).strip() for item in data if item is not None and str(item).strip()]
        if items and prefix:
            result[prefix] = items
        return result
    if isinstance(data, dict):
        for key, value in data.items():
            child_prefix = f"{prefix}/{key}" if prefix else str(key)
            result.update(_flatten_yaml(value, child_prefix))
    return result


def _find_common_root(paths: list[PurePosixPath]) -> PurePosixPath | None:
    """Find a single common root directory shared by all paths, if any.

    Returns the common prefix only if all paths share the same top-level
    directory (e.g. ``wildcards/a.txt``, ``wildcards/sub/b.txt`` → ``wildcards``).
    Returns ``None`` if paths are at the root or have no common directory.
    """
    if not paths:
        return None
    # Get parent directories of all files
    parents = [p.parts[:-1] for p in paths]
    if not all(len(parts) > 0 for parts in parents):
        # Some files are at the root level — no common prefix to strip
        return None
    # Find common prefix parts
    first = parents[0]
    common_len = 0
    for i in range(len(first)):
        if all(len(parts) > i and parts[i] == first[i] for parts in parents):
            common_len = i + 1
        else:
            break
    if common_len == 0:
        return None
    return PurePosixPath(*first[:common_len])


def load_wildcards_from_dirs(
    dirs: list[str], raw: bool = False
) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Read .txt/.yaml/.yml files recursively and return (wildcards, sources).

    Returns a tuple of:
    - ``wildcards``: ``{name: [lines]}`` — the wildcard entries
    - ``sources``: ``{name: "txt"|"yaml"}`` — origin format per entry

    Wildcard names use the relative path from the configured directory,
    with the extension removed and ``/`` as separator
    (e.g. ``hair/color`` for ``<dir>/hair/color.txt``).

    - Recursively scans all subdirectories
    - Skips directories that don't exist
    - When ``raw=False`` (default): skips comment lines (``#``) and empty lines.
      Suitable for prompt expansion / random selection.
    - When ``raw=True``: preserves all .txt content as-is (comments, blank lines)
      so the editor can round-trip a file without losing user formatting.
      YAML files are unaffected by this flag.
    - Skips symlinks that resolve outside the specified directory
    - Later directories override earlier ones for same-named files
    """
    result: dict[str, list[str]] = {}
    sources: dict[str, str] = {}
    for dir_path_str in dirs:
        dir_path = Path(dir_path_str)
        if not dir_path.is_dir():
            continue
        resolved_dir = dir_path.resolve()
        try:
            entries = sorted(dir_path.rglob("*.txt"))
        except OSError:
            continue
        for entry in entries:
            if not entry.is_file():
                continue
            # Security: skip symlinks pointing outside the directory
            if entry.is_symlink():
                try:
                    resolved = entry.resolve()
                    if not str(resolved).startswith(str(resolved_dir) + os.sep):
                        continue
                except OSError:
                    continue
            # Build wildcard name from relative path (POSIX-style, no .txt)
            try:
                rel = entry.relative_to(dir_path)
            except ValueError:
                continue
            name = str(PurePosixPath(rel.with_suffix("")))
            try:
                text = entry.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if raw:
                # Preserve every line including comments / blanks. ``splitlines``
                # already drops the trailing line terminator, so a file ending in
                # "\n" does not introduce a phantom empty entry.
                lines = text.splitlines()
                # Always register the entry — even an empty file should be
                # editable from the manager.
                result[name] = lines
                sources[name] = "txt"
            else:
                lines = [
                    line.strip()
                    for line in text.splitlines()
                    if line.strip() and not line.strip().startswith("#")
                ]
                if lines:
                    result[name] = lines
                    sources[name] = "txt"
        # --- YAML wildcard files (.yaml / .yml) ---
        if _yaml is not None:
            for ext in ("*.yaml", "*.yml"):
                try:
                    yaml_entries = sorted(dir_path.rglob(ext))
                except OSError:
                    continue
                for entry in yaml_entries:
                    if not entry.is_file():
                        continue
                    if entry.is_symlink():
                        try:
                            resolved = entry.resolve()
                            if not str(resolved).startswith(str(resolved_dir) + os.sep):
                                continue
                        except OSError:
                            continue
                    try:
                        rel = entry.relative_to(dir_path)
                    except ValueError:
                        continue
                    root_name = str(PurePosixPath(rel.with_suffix("")))
                    try:
                        text = entry.read_text(encoding="utf-8", errors="replace")
                        data = _yaml.safe_load(text)
                    except Exception as exc:
                        logger.debug("wildcard file skipped, its entries will not exist: %s", exc)
                        continue
                    if not isinstance(data, (dict, list)):
                        continue
                    flattened = _flatten_yaml(data, root_name)
                    result.update(flattened)
                    for key in flattened:
                        sources[key] = "yaml"
    return result, sources


def load_wildcards_from_zip(data: bytes) -> dict[str, list[str]]:
    """Extract wildcard files (.txt / .yaml / .yml) from a ZIP archive in memory.

    Wildcard names preserve directory structure relative to the ZIP root
    (e.g. ``hair/color`` for ``hair/color.txt`` inside the ZIP).
    If all files share a single common root directory, it is stripped
    automatically (e.g. ``wildcards/hair/color.txt`` → ``hair/color``).

    - Recursively processes wildcard files at any depth
    - Skips comment lines (``#``) and empty lines (for .txt)
    - Skips entries with ``..`` in the path (path traversal prevention)
    - Rejects archives whose total uncompressed size exceeds 50 MB
    """
    _SUPPORTED_SUFFIXES = {".txt"}
    if _yaml is not None:
        _SUPPORTED_SUFFIXES.update({".yaml", ".yml"})

    result: dict[str, list[str]] = {}
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        # Zip bomb check: sum of uncompressed sizes
        total_size = sum(info.file_size for info in zf.infolist())
        if total_size > _ZIP_MAX_UNCOMPRESSED:
            raise ValueError(
                f"ZIP uncompressed size ({total_size} bytes) exceeds limit "
                f"({_ZIP_MAX_UNCOMPRESSED} bytes)"
            )

        # Collect all wildcard paths to determine common root prefix
        wc_paths: list[PurePosixPath] = []
        for info in zf.infolist():
            if info.is_dir():
                continue
            p = PurePosixPath(info.filename)
            if ".." in p.parts:
                continue
            if p.suffix.lower() in _SUPPORTED_SUFFIXES:
                wc_paths.append(p)

        # Strip single common root directory (e.g. "wildcards/")
        common_prefix = _find_common_root(wc_paths)

        for info in zf.infolist():
            if info.is_dir():
                continue
            p = PurePosixPath(info.filename)
            if ".." in p.parts:
                continue
            suffix = p.suffix.lower()
            if suffix not in _SUPPORTED_SUFFIXES:
                continue
            # Build wildcard name from relative path (strip common root)
            rel = p.relative_to(common_prefix) if common_prefix else p
            try:
                raw = zf.read(info.filename)
                text = raw.decode("utf-8", errors="replace")
            except Exception as exc:
                logger.debug("wildcard zip member unreadable, skipped: %s", exc)
                continue

            if suffix in (".yaml", ".yml"):
                # YAML: flatten hierarchy into wildcard paths
                try:
                    yaml_data = _yaml.safe_load(text)
                except Exception as exc:
                    logger.debug("wildcard YAML unparseable, skipped: %s", exc)
                    continue
                if not isinstance(yaml_data, (dict, list)):
                    continue
                root_name = str(rel.with_suffix(""))
                flattened = _flatten_yaml(yaml_data, root_name)
                result.update(flattened)
            else:
                # .txt: one entry per non-empty, non-comment line
                name = str(rel.with_suffix(""))
                lines = [
                    line.strip()
                    for line in text.splitlines()
                    if line.strip() and not line.strip().startswith("#")
                ]
                if lines:
                    result[name] = lines
    return result
