"""GenAI HEF model download and status facade with compatibility wrappers."""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request
from urllib.request import urlopen as _stdlib_urlopen

try:
    from .genai_types import GenAIModelInfo, GenAIModelType
    from .model_download_exec import download_hef as _download_hef
    from .model_download_exec import get_hef_path as _get_hef_path
    from .model_download_exec import get_model_status as _get_model_status
    from .model_download_exec import is_hef_available as _is_hef_available
    from .model_manifest_parse import parse_models_rst
    from .model_registry import BUNDLED_ROWS as _BUNDLED_ROWS
    from .model_registry import classify_by_filename as _classify_by_filename_impl
    from .model_registry import rows_to_registry as _rows_to_registry_impl
except ImportError:  # pragma: no cover - top-level extension import path
    from genai_types import GenAIModelInfo, GenAIModelType
    from model_download_exec import download_hef as _download_hef
    from model_download_exec import get_hef_path as _get_hef_path
    from model_download_exec import get_model_status as _get_model_status
    from model_download_exec import is_hef_available as _is_hef_available
    from model_manifest_parse import parse_models_rst
    from model_registry import BUNDLED_ROWS as _BUNDLED_ROWS
    from model_registry import classify_by_filename as _classify_by_filename_impl
    from model_registry import rows_to_registry as _rows_to_registry_impl

logger = logging.getLogger(__name__)

_DEFAULT_HEF_DIR = os.environ.get("HAILO_HEF_DIR", str(Path.home() / "hailo_models"))
_GENAI_BASE_URL = "https://dev-public.hailo.ai"
_HAILORT_VERSION = "5.3.0"
_USER_AGENT = "YU-AI-Manager/2.56 (Hailo GenAI Download)"
_CACHE_DIR = Path.home() / ".cache" / "yu_ai_manager"
_urlopen = _stdlib_urlopen
_MODELS_RST_URL_TEMPLATES = (
    "https://raw.githubusercontent.com/hailo-ai/hailo_model_zoo_genai/v{version}/docs/MODELS.rst",
    "https://raw.githubusercontent.com/hailo-ai/hailo_model_zoo_genai/{version}/docs/MODELS.rst",
    "https://raw.githubusercontent.com/hailo-ai/hailo_model_zoo_genai/main/docs/MODELS.rst",
)


def _parse_models_rst(text: str):
    return parse_models_rst(text)


def _classify_by_filename(filename: str) -> GenAIModelType:
    return _classify_by_filename_impl(filename)


def _cache_path(version: str) -> Path:
    return _CACHE_DIR / f"hailo_models_{version}.json"


def _save_cached_manifest(version: str, rows) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": version,
            "rows": [{"section": row.section, "hef_filename": row.hef_filename, "url": row.url} for row in rows],
        }
        _cache_path(version).write_text(json.dumps(payload), encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to write hailo models cache: %s", exc)


def _load_cached_manifest(version: str):
    path = _cache_path(version)
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


def _fetch_remote_manifest(version: str, timeout: float = 5.0):
    for template in _MODELS_RST_URL_TEMPLATES:
        url = template.format(version=version)
        req = Request(url, headers={"User-Agent": _USER_AGENT})
        try:
            with _urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8")
        except (HTTPError, URLError, OSError, TimeoutError) as exc:
            logger.warning("Failed to fetch %s: %s", url, exc)
    return None


def _rows_to_registry(rows):
    return _rows_to_registry_impl(rows)


def _build_models_registry(version: str | None = None, *, remote: bool = True):
    version = version or _HAILORT_VERSION
    text = _fetch_remote_manifest(version) if remote else None
    if text:
        rows = _parse_models_rst(text)
        if rows:
            registry = _rows_to_registry(rows)
            if registry:
                _save_cached_manifest(version, rows)
                return registry
    cached = _load_cached_manifest(version)
    if cached:
        registry = _rows_to_registry(cached)
        if registry:
            return registry
    logger.info(
        "Using bundled Hailo GenAI model registry (v%s); remote fetch and cache both unavailable",
        version,
    )
    return _rows_to_registry(_BUNDLED_ROWS)


# Import time is local-only, deliberately. `_fetch_remote_manifest` is a
# blocking `urlopen`, and its `timeout=` covers the socket but NOT the
# `getaddrinfo` that precedes it -- so on a host that cannot resolve DNS each of
# the three URL templates stalls for the resolver's full budget. Under Quart the
# import happens inside a route handler (`openai_models` imports this module
# lazily), i.e. ON the event loop: the whole server stops answering for ~10s+,
# and every other in-flight request dies at its client timeout. That is exactly
# what CI parity Phase 3 reported -- ten endpoints, all ReadTimeout, and py-spy
# caught all nineteen blocked samples in this one stack (`33304722835`).
GENAI_MODELS: dict[str, GenAIModelInfo] = _build_models_registry(remote=False)

_remote_refresh_started = False


def _refresh_registry_from_remote() -> None:
    """Fetch the manifest and merge it into `GENAI_MODELS` **in place**.

    In place because every consumer imported the dict object itself; rebinding
    the module global would leave them all reading the stale one. `update`
    rather than `clear`+`update`: a remote that lost a model must not delete a
    HEF entry the user still has on disk.
    """
    try:
        registry = _build_models_registry()
    except Exception as exc:  # pragma: no cover - defensive: background thread
        logger.warning("Hailo GenAI manifest refresh failed: %s", exc)
        return
    if registry:
        GENAI_MODELS.update(registry)


def start_remote_registry_refresh() -> None:
    """Start the one-shot remote refresh on a daemon thread. Never blocks.

    Call this from route registration, not from a request: the point is that no
    caller ever waits on it. Idempotent -- the second call is a no-op.
    """
    global _remote_refresh_started
    if _remote_refresh_started:
        return
    _remote_refresh_started = True
    threading.Thread(
        target=_refresh_registry_from_remote,
        name="hailo-genai-manifest-refresh",
        daemon=True,
    ).start()



def get_hef_path(model_name: str, hef_dir: str | None = None) -> Path:
    return _get_hef_path(model_name, GENAI_MODELS, _DEFAULT_HEF_DIR, hef_dir)


def is_hef_available(model_name: str, hef_dir: str | None = None) -> bool:
    return _is_hef_available(model_name, GENAI_MODELS, _DEFAULT_HEF_DIR, hef_dir)


def get_model_status(hef_dir: str | None = None) -> dict:
    return _get_model_status(GENAI_MODELS, _DEFAULT_HEF_DIR, hef_dir)


def download_hef(model_name: str, hef_dir: str | None = None, progress_callback=None) -> Path:
    return _download_hef(model_name, GENAI_MODELS, _DEFAULT_HEF_DIR, _USER_AGENT, hef_dir, progress_callback)
