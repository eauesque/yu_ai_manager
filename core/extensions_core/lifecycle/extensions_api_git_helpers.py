"""Helper functions for extension git operations."""

import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from .extensions_admin import git_pull_ff_only

_ALLOWED_GIT_SCHEMES = {"https"}


def validate_git_url(git_url: str) -> str | None:
    """Return error message if git URL uses a disallowed scheme, else None."""
    try:
        parsed = urlparse(git_url)
    except Exception:
        return "Invalid URL format"
    if not parsed.scheme:
        return "URL must include a scheme (https://...)"
    if parsed.scheme.lower() not in _ALLOWED_GIT_SCHEMES:
        return f"Disallowed URL scheme: {parsed.scheme!r}. Only https:// is allowed."
    if not parsed.netloc:
        return "URL must include a hostname"
    return None


def repo_name_from_git_url(git_url: str) -> str:
    # urlparse isolates the path component, stripping query (?...) and fragment (#...)
    name = Path(urlparse(git_url).path).name
    if name.endswith(".git"):
        name = name[:-4]
    return name


def clone_repo(git_url: str, target_dir: Path) -> tuple[dict, int]:
    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", git_url, str(target_dir)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        if result.returncode != 0:
            return {"error": "git clone failed", "detail": result.stderr[:500]}, 500
    except FileNotFoundError:
        return {"error": "git is not installed on this system"}, 500
    except subprocess.TimeoutExpired:
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        return {"error": "git clone timed out (120s)"}, 500
    return {}, 200


def pull_repo_ff_only(ext_dir: Path) -> tuple[dict, int, str]:
    try:
        result = git_pull_ff_only(ext_dir, timeout=60)
        if result.returncode != 0:
            return {"error": "git pull failed", "detail": result.stderr[:500]}, 500, ""
    except subprocess.TimeoutExpired:
        return {"error": "git pull timed out"}, 500, ""

    stdout = result.stdout.strip()
    return {}, 200, stdout
