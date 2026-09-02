"""Source browser security layer -- path validation, access control definitions.

Provides path resolution, extension whitelist, blocked patterns,
and file/directory access checks for the source browser.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

# ── Project root ────────────────────────────────
_PROJECT_ROOT: Path | None = None


def _get_project_root() -> Path:
    global _PROJECT_ROOT
    if _PROJECT_ROOT is None:
        _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    return _PROJECT_ROOT


# ── Security definitions ────────────────────────────────

# Allowed file extensions (whitelist)
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".ts", ".js", ".mjs", ".tsx", ".jsx",
    ".html", ".css", ".scss",
    ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini",
    ".md", ".txt", ".rst",
    ".sh", ".bat", ".cmd", ".ps1",
    ".sql", ".gitignore", ".gitattributes",
    ".editorconfig", ".prettierrc", ".eslintrc",
})

# Filenames allowed without extensions
ALLOWED_EXTENSIONLESS: frozenset[str] = frozenset({
    "Dockerfile", "Makefile", "Procfile", "VERSION",
    "LICENSE", "CHANGELOG", "TODO",
    ".gitignore", ".gitattributes", ".editorconfig",
})

# Blocked filename patterns (fnmatch)
BLOCKED_PATTERNS: tuple[str, ...] = (
    # Sensitive files
    "*.env", ".env.*", "secret.salt", "*.key", "*.pem", "*.cert", "*.crt",
    "config.json", "config_*.json",
    "credentials*", "*token*", "*secret*",
    # Binary / large files
    "*.db", "*.sqlite", "*.sqlite3", "*.pyc", "*.pyo",
    "*.whl", "*.egg", "*.tar.gz", "*.zip", "*.7z",
    "*.png", "*.jpg", "*.jpeg", "*.gif", "*.webp", "*.ico", "*.svg",
    "*.mp4", "*.webm", "*.mov", "*.avi",
    "*.woff", "*.woff2", "*.ttf", "*.eot",
    "*.hef", "*.onnx", "*.bin", "*.pt", "*.safetensors",
    # Lock files
    "pnpm-lock.yaml", "package-lock.json", "yarn.lock",
    "uv.lock", "poetry.lock", "Pipfile.lock",
)

# Blocked directory names
BLOCKED_DIRS: frozenset[str] = frozenset({
    ".git", "__pycache__", "node_modules", "venv", ".venv",
    "dist", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".tox", ".eggs", "*.egg-info",
    "src-tauri",       # Rust binary build
    "data",            # DB files
    "reports",         # Test reports
    "screenshots",     # Screenshots
    "backups",         # DB backups
})

# Read limits
MAX_FILE_SIZE_BYTES: int = 1 * 1024 * 1024  # 1 MB
MAX_LINES: int = 2000
MAX_TREE_DEPTH: int = 6
MAX_SEARCH_RESULTS: int = 50


# ── Path validation ────────────────────────────────

def _resolve_safe(rel_path: str) -> tuple[Path | None, str | None]:
    """Resolve a relative path to an absolute path within the project root.

    Returns:
        (resolved_path, error_message) -- one side is None
    """
    root = _get_project_root()

    # Empty path refers to root itself
    if not rel_path or rel_path in (".", "/", "\\"):
        return root, None

    # Path injection prevention: null byte
    if "\x00" in rel_path:
        return None, "不正なパスです"

    # Normalize
    cleaned = rel_path.replace("\\", "/").lstrip("/")
    target = (root / cleaned).resolve()

    # Traversal check
    try:
        target.relative_to(root)
    except ValueError:
        return None, "プロジェクトルート外へのアクセスは禁止されています"

    return target, None


def _is_dir_blocked(name: str) -> bool:
    """Check whether a directory name is blocked."""
    if name in BLOCKED_DIRS:
        return True
    return any("*" in pattern and fnmatch.fnmatch(name, pattern) for pattern in BLOCKED_DIRS)


def _is_file_blocked(name: str) -> bool:
    """Check whether a filename matches a blocked pattern."""
    lower = name.lower()
    return any(fnmatch.fnmatch(lower, pattern.lower()) for pattern in BLOCKED_PATTERNS)


def _is_file_allowed(path: Path) -> bool:
    """Check whether a file is allowed for reading."""
    name = path.name

    # Block list check
    if _is_file_blocked(name):
        return False

    # Special allowance for extensionless files
    if name in ALLOWED_EXTENSIONLESS:
        return True

    # Extension whitelist
    ext = path.suffix.lower()
    if not ext:
        return False
    return ext in ALLOWED_EXTENSIONS
