"""Manifest cache and fetch helpers for Hailo GenAI models."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request
from urllib.request import urlopen as _urlopen

logger = logging.getLogger(__name__)

CACHE_DIR = Path.home() / ".cache" / "yu_ai_manager"
USER_AGENT = "YU-AI-Manager/2.56 (Hailo GenAI Download)"
MODELS_RST_URL_TEMPLATES = (
    "https://raw.githubusercontent.com/hailo-ai/hailo_model_zoo_genai/v{version}/docs/MODELS.rst",
    "https://raw.githubusercontent.com/hailo-ai/hailo_model_zoo_genai/{version}/docs/MODELS.rst",
    "https://raw.githubusercontent.com/hailo-ai/hailo_model_zoo_genai/main/docs/MODELS.rst",
)


def cache_path(version: str) -> Path:
    return CACHE_DIR / f"hailo_models_{version}.json"


def save_cached_manifest(version: str, rows) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": version,
            "rows": [{"section": row.section, "hef_filename": row.hef_filename, "url": row.url} for row in rows],
        }
        cache_path(version).write_text(json.dumps(payload), encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to write hailo models cache: %s", exc)


def load_cached_manifest(version: str) -> list | None:
    path = cache_path(version)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("Failed to read hailo models cache: %s", exc)
        return None
    if payload.get("version") != version:
        return None
    rows = payload.get("rows")
    return rows if isinstance(rows, list) else None


def fetch_remote_manifest(version: str, timeout: float = 5.0) -> str | None:
    for template in MODELS_RST_URL_TEMPLATES:
        url = template.format(version=version)
        req = Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with _urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8")
        except (HTTPError, URLError, OSError, TimeoutError) as exc:
            logger.warning("Failed to fetch %s: %s", url, exc)
    return None
