"""Thin HTTP helper for bridge extensions.

Uses only ``urllib.request`` — no extra dependencies.
Designed to be reused by sd-webui-bridge, comfyui-bridge, nai-api-bridge, etc.
"""

from __future__ import annotations

import contextlib
import json
import logging
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_UA = "yu-ai-manager/BridgeHTTPClient"


# ------------------------------------------------------------------
# Exceptions
# ------------------------------------------------------------------

class BridgeConnectionError(Exception):
    """Raised when the bridge target is unreachable."""


_ALLOWED_SCHEMES = ("http://", "https://")


def _require_http_url(base_url: str) -> str:
    """Reject anything `urlopen` would treat as a non-HTTP scheme.

    `urllib.request.urlopen` honours `file://`, `ftp://` and `data:` as well as
    HTTP. Every bridge base URL here comes from config, so a malformed or
    hostile value would turn a "call the local SD server" path into a local
    file read. One check at construction covers all nine `urlopen` call sites
    in this module, which is why it lives here and not at each of them.
    """
    url = (base_url or "").strip()
    if not url.lower().startswith(_ALLOWED_SCHEMES):
        raise ValueError(
            f"bridge base_url must start with http:// or https://, got {url[:32]!r}"
        )
    return url


class BridgeHTTPError(Exception):
    """Raised when the bridge target returns a non-2xx status."""

    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status}: {body[:200]}")


# ------------------------------------------------------------------
# Client
# ------------------------------------------------------------------

class BridgeHTTPClient:
    """Simple JSON-over-HTTP client with a fixed *base_url*.

    Parameters
    ----------
    base_url:
        Root URL of the target service (e.g. ``http://127.0.0.1:7860``).
        Trailing slashes are stripped automatically.
    timeout:
        Default request timeout in seconds.
    """

    def __init__(self, base_url: str, timeout: float = 15.0,
                 default_headers: dict[str, str] | None = None) -> None:
        self.base_url = _require_http_url(base_url).rstrip("/")
        self.timeout = timeout
        self._default_headers = default_headers or {}

    # -- public API -------------------------------------------------

    def get(self, path: str, *, timeout: float | None = None) -> dict[str, Any]:
        """Send a GET request and return the parsed JSON body."""
        url = self._url(path)
        req = urllib.request.Request(url, method="GET")
        req.add_header("Accept", "application/json")
        self._apply_headers(req)
        return self._fetch(req, timeout or self.timeout)

    def post_json(
        self,
        path: str,
        body: dict[str, Any],
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Send a POST request with a JSON body and return the parsed JSON."""
        url = self._url(path)
        payload = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        self._apply_headers(req)
        return self._fetch(req, timeout or self.timeout)

    def post_json_bytes(
        self,
        path: str,
        body: dict[str, Any],
        *,
        timeout: float | None = None,
    ) -> bytes:
        """Send a POST with JSON body and return raw bytes (for ZIP responses)."""
        url = self._url(path)
        payload = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        self._apply_headers(req)
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            body_text = ""
            with contextlib.suppress(Exception):
                body_text = exc.read().decode("utf-8", errors="replace")
            raise BridgeHTTPError(exc.code, body_text) from exc
        except urllib.error.URLError as exc:
            raise BridgeConnectionError(
                f"Cannot connect to {self.base_url}: {exc.reason}"
            ) from exc
        except OSError as exc:
            raise BridgeConnectionError(
                f"Cannot connect to {self.base_url}: {exc}"
            ) from exc

    def get_bytes(self, path: str, *, timeout: float | None = None) -> bytes:
        """Send a GET request and return raw bytes (for image retrieval)."""
        url = self._url(path)
        req = urllib.request.Request(url, method="GET")
        self._apply_headers(req)
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            body = ""
            with contextlib.suppress(Exception):
                body = exc.read().decode("utf-8", errors="replace")
            raise BridgeHTTPError(exc.code, body) from exc
        except urllib.error.URLError as exc:
            raise BridgeConnectionError(
                f"Cannot connect to {self.base_url}: {exc.reason}"
            ) from exc
        except OSError as exc:
            raise BridgeConnectionError(
                f"Cannot connect to {self.base_url}: {exc}"
            ) from exc

    def check_connectivity(self) -> bool:
        """Return ``True`` if *base_url* is reachable (GET /)."""
        try:
            req = urllib.request.Request(self.base_url + "/", method="GET")
            self._apply_headers(req)
            with urllib.request.urlopen(req, timeout=min(self.timeout, 5.0)):
                pass
            return True
        except Exception:
            return False

    # -- internals --------------------------------------------------

    def _apply_headers(self, req: urllib.request.Request) -> None:
        if not req.has_header("User-agent"):
            req.add_header("User-Agent", _DEFAULT_UA)
        for key, val in self._default_headers.items():
            req.add_header(key, val)

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return self.base_url + path

    def _fetch(self, req: urllib.request.Request, timeout: float) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = ""
            with contextlib.suppress(Exception):
                body = exc.read().decode("utf-8", errors="replace")
            raise BridgeHTTPError(exc.code, body) from exc
        except urllib.error.URLError as exc:
            raise BridgeConnectionError(
                f"Cannot connect to {self.base_url}: {exc.reason}"
            ) from exc
        except OSError as exc:
            raise BridgeConnectionError(
                f"Cannot connect to {self.base_url}: {exc}"
            ) from exc

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Non-JSON response from %s: %s", req.full_url, raw[:200])
            return {"_raw": raw}
