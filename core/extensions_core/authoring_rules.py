"""Validation and path helpers for extension authoring."""

import re
from pathlib import Path

_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
_NAME_MAX = 50
_FILENAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
_PROHIBITED_PREFIXES = ("builtin-",)

# File type definitions: (subdirectory, extension, max_size_bytes)
FILE_TYPES: dict[str, tuple[str, str, int]] = {
    "entrypoint": (".", ".py", 51200),
    "template": ("templates", ".html", 51200),
    "static_css": ("static", ".css", 51200),
    "static_js": ("static", ".js", 51200),
    "config": (".", ".json", 10240),
    "readme": (".", ".md", 20480),
}


def extensions_dir() -> Path:
    """Get the extensions directory from config with a safe fallback."""
    try:
        from core.services_core.db_api import get_config

        config = get_config() or {}
        return Path(config.get("extensions_dir", "extensions"))
    except Exception:
        return Path("extensions")


def validate_name(name: str) -> str | None:
    if not name:
        return "Extension name must not be empty"
    if len(name) > _NAME_MAX:
        return f"Extension name too long (max {_NAME_MAX} characters)"
    if not _NAME_RE.match(name):
        return "Extension name must contain only lowercase letters, numbers, and hyphens"
    for prefix in _PROHIBITED_PREFIXES:
        if name.startswith(prefix):
            return f"Extension name must not start with '{prefix}'"
    return None


def validate_file_type(file_type: str) -> str | None:
    if file_type not in FILE_TYPES:
        valid = ", ".join(sorted(FILE_TYPES.keys()))
        return f"Invalid file_type '{file_type}'. Must be one of: {valid}"
    return None


def validate_filename(filename: str, file_type: str) -> str | None:
    if not filename:
        return "Filename must not be empty"
    if not _FILENAME_RE.match(filename):
        return "Filename must contain only letters, numbers, hyphens, and underscores"
    if len(filename) > 100:
        return "Filename too long (max 100 characters)"
    if file_type == "config" and filename != "extension":
        return "Config file must be named 'extension' (extension.json)"
    if file_type == "readme" and filename != "README":
        return "Readme file must be named 'README' (README.md)"
    return None


def ext_dir(name: str) -> Path:
    return extensions_dir() / f"custom-{name}"


def resolve_file_path(name: str, file_type: str, filename: str) -> Path:
    """Resolve the physical file path from validated inputs."""
    subdir, ext, _ = FILE_TYPES[file_type]
    base = ext_dir(name)
    if subdir == ".":
        return base / f"{filename}{ext}"
    if file_type == "template":
        return base / subdir / name.replace("-", "_") / f"{filename}{ext}"
    return base / subdir / f"{filename}{ext}"
