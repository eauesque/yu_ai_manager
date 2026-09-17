"""Canonical extension entry-path validation shared by host and workers."""

from pathlib import Path


def resolve_extension_entry(ext_dir: Path, entry: str) -> Path:
    if not entry or Path(entry).is_absolute() or ".." in Path(entry).parts:
        raise ValueError("extension entry path is unsafe")
    root = ext_dir.resolve(strict=True)
    path = ext_dir / entry
    if path.is_symlink() or not path.is_file():
        raise ValueError("extension entry must be a regular file")
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError("extension entry escapes extension directory")
    return resolved
