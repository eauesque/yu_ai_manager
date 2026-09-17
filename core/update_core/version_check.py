"""Check for available updates from GitHub releases."""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request

from core.update_core.detect import PROJECT_ROOT, detect_install_type

logger = logging.getLogger(__name__)

# Cache: {"result": dict, "ts": float}
_cache: dict = {}
_CACHE_TTL = 600  # 10 minutes

_GITHUB_REPO = "eauesque/yu_ai_manager"
_RELEASES_URL = f"https://api.github.com/repos/{_GITHUB_REPO}/releases/latest"


def _parse_version(v: str) -> tuple[int, ...]:
    """Parse a version string like '4.20.0' into a comparable tuple."""
    v = v.strip().lstrip("v")
    parts: list[int] = []
    for seg in v.split("."):
        try:
            parts.append(int(seg))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _read_current_version() -> str:
    """Read the current version from the VERSION file."""
    version_path = os.path.join(PROJECT_ROOT, "VERSION")
    try:
        with open(version_path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "0.0.0"


def check_for_update() -> dict:
    """Check GitHub for the latest release and compare with current version.

    Returns a dict with update information.  Results are cached for 10 minutes.
    Network errors are handled gracefully (update_available=False with error).
    """
    now = time.time()
    if _cache.get("result") and (now - _cache.get("ts", 0)) < _CACHE_TTL:
        return _cache["result"]

    current = _read_current_version()
    install_type = detect_install_type()

    result: dict = {
        "current": current,
        "latest": current,
        "update_available": False,
        "release_url": "",
        "release_notes": "",
        "published_at": "",
        "install_type": install_type,
    }

    try:
        req = urllib.request.Request(
            _RELEASES_URL,
            headers={
                "User-Agent": f"YU-AI-Manager/{current}",
                "Accept": "application/vnd.github+json",
            },
        )
        # 5s, not 15: an update poll behind a UI panel outlived every caller's
        # patience at 15. The route's own deadline is the outer bound, since
        # this timeout does not cover getaddrinfo.
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        tag = data.get("tag_name", "")
        latest = tag.lstrip("v")
        result["latest"] = latest
        result["release_url"] = data.get("html_url", "")
        result["release_notes"] = data.get("body", "") or ""
        result["published_at"] = data.get("published_at", "")

        if _parse_version(latest) > _parse_version(current):
            result["update_available"] = True

        # Docker-specific hint
        if install_type == "docker":
            result["docker_command"] = (
                f"docker pull ghcr.io/{_GITHUB_REPO}:latest"
            )

        # Portable-specific: include download URL for the ZIP asset
        if install_type == "portable":
            assets = data.get("assets", [])
            for asset in assets:
                name = asset.get("name", "").lower()
                if ("portable" in name and "win" in name
                        and "amd64" in name and name.endswith(".zip")):
                    result["portable_download_url"] = (
                        asset["browser_download_url"]
                    )
                    break

    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        logger.warning("Update check failed: %s", exc)
        result["error"] = str(exc)
    except Exception as exc:
        logger.warning("Unexpected error during update check: %s", exc)
        result["error"] = str(exc)

    _cache["result"] = result
    _cache["ts"] = now
    return result
