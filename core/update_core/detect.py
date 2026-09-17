"""Detect the installation type of YU AI Manager."""

import logging
import os

logger = logging.getLogger(__name__)

# Resolved once and cached
_cached_install_type: str | None = None

# PROJECT_ROOT: directory containing web_ui.py
PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)


def detect_install_type() -> str:
    """Return the installation type: git, tauri, docker, portable, or unknown.

    Result is cached after first call.
    """
    global _cached_install_type
    if _cached_install_type is not None:
        return _cached_install_type

    if os.environ.get("YU_TAURI_PIN"):
        _cached_install_type = "tauri"
    elif os.path.exists("/.dockerenv") or os.environ.get("DOCKER_CONTAINER"):
        _cached_install_type = "docker"
    elif os.path.exists(os.path.join(PROJECT_ROOT, ".git")):
        _cached_install_type = "git"
    elif os.path.exists(os.path.join(PROJECT_ROOT, "python", "python.exe")):
        # Embedded Python indicates a portable/zip distribution
        _cached_install_type = "portable"
    else:
        _cached_install_type = "unknown"

    logger.info("Detected install type: %s", _cached_install_type)
    return _cached_install_type
