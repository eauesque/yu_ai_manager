"""HTTP fetching for the extension index."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_USER_AGENT = "YU-AI-Manager/2.61.0"
_TIMEOUT = 10


def fetch_json(url: str) -> Any:
    """Fetch JSON from a URL.

    Sends an HTTP GET with an appropriate User-Agent header.
    User-Agent is required to prevent Cloudflare blocks.
    """
    # URL scheme validation (SSRF prevention)
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Disallowed URL scheme: {parsed.scheme!r}")
    if not parsed.hostname:
        raise ValueError("URL must have a valid hostname")

    req = Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urlopen(req, timeout=_TIMEOUT) as resp:
            data = resp.read().decode("utf-8")
            return json.loads(data)
    except URLError as exc:
        logger.warning("Failed to fetch %s: %s", url, exc)
        raise
    except json.JSONDecodeError as exc:
        logger.warning("Invalid JSON from %s: %s", url, exc)
        raise
