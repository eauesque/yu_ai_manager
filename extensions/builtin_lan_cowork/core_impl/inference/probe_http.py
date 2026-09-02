"""HTTP/config helpers for inference probing."""

from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


def get_llm_endpoints() -> dict[str, dict]:
    try:
        from core.configuration.api import load_config  # type: ignore

        cfg = load_config()
        return cfg.get("llm_endpoints") or {}
    except Exception:
        logger.debug("Failed to load llm_endpoints from config", exc_info=True)
        return {}


class HttpResponse:
    """Minimal response wrapper returned by http_get."""

    def __init__(self, status_code: int, body: bytes) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> Any:
        return json.loads(self._body)


def http_get(url: str, timeout: float = 3.0) -> HttpResponse | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "yu-ai-manager/probe"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return HttpResponse(status_code=resp.status, body=resp.read())
    except Exception:
        logger.debug("HTTP GET failed: %s", url, exc_info=True)
        return None
