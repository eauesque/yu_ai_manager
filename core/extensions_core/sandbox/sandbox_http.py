"""SandboxedHTTPClient: HTTP client proxy for extensions.

network:local -> localhost/LAN only
network:internet -> all hosts (but private IPs blocked for SSRF prevention)
no permission -> all requests denied
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class SandboxHTTPError(Exception):
    """Error raised by SandboxedHTTPClient."""


# Default timeout (seconds)
_DEFAULT_TIMEOUT = 30
_MAX_TIMEOUT = 120

# User-Agent (Cloudflare bypass)
_USER_AGENT = "YU-AI-Manager/Extension-HTTP-Client"


def _resolve_ips(hostname: str) -> list[str]:
    """Resolve a host once and return every address it may connect to."""
    try:
        return [str(ipaddress.ip_address(hostname))]
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        return []
    return list(dict.fromkeys(info[4][0] for info in infos))


def _is_private_ip(hostname: str) -> bool:
    """Return True unless every resolved address is globally routable."""
    ips = _resolve_ips(hostname)
    return not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips)


def _is_loopback_or_lan(hostname: str, ips: list[str] | None = None) -> bool:
    """Check whether a hostname is localhost or a private IP."""
    ips = _resolve_ips(hostname) if ips is None else ips
    return bool(ips) and all(not ipaddress.ip_address(ip).is_global for ip in ips)


class SandboxedHTTPClient:
    """HTTP client proxy for extensions.

    Restricts access targets according to scope.

    Args:
        caller_name: Extension name
        scope: "local", "internet", or None (all denied)
        allowed_hosts: Retained for compatibility; it cannot bypass IP scope checks.
    """

    def __init__(
        self,
        caller_name: str,
        scope: str | None = None,
        allowed_hosts: list[str] | None = None,
    ) -> None:
        self._caller = caller_name
        self._scope = scope
        self._allowed_hosts = set(allowed_hosts or [])

    def _check_url(self, url: str) -> tuple[Any, str]:
        """Check a URL and pin the request to one validated address."""
        if self._scope is None:
            raise SandboxHTTPError(
                f"Extension '{self._caller}' には network 権限がありません"
            )

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise SandboxHTTPError(
                f"許可されていないプロトコル: {parsed.scheme}"
            )

        hostname = parsed.hostname or ""
        if not hostname or parsed.username or parsed.password:
            raise SandboxHTTPError("無効な URL")
        ips = _resolve_ips(hostname)
        if not ips:
            raise SandboxHTTPError(f"ホストを解決できません: {hostname}")

        if self._scope == "local":
            # local scope: localhost/LAN only
            if not _is_loopback_or_lan(hostname, ips):
                raise SandboxHTTPError(
                    f"Extension '{self._caller}' (network:local) は "
                    f"外部ホスト '{hostname}' にアクセスできません"
                )
        elif self._scope == "internet":
            # internet scope: all hosts OK but private IPs blocked for SSRF prevention
            if any(not ipaddress.ip_address(ip).is_global for ip in ips):
                raise SandboxHTTPError(
                    f"SSRF 防止: Extension '{self._caller}' は "
                    f"プライベート IP '{hostname}' にアクセスできません"
                )
        else:
            raise SandboxHTTPError(
                f"不明な network scope: {self._scope}"
            )
        return parsed, ips[0]

    def _ensure_headers(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Auto-set User-Agent header + enforce timeout limits."""
        headers = kwargs.get("headers", {})
        if isinstance(headers, dict) and "User-Agent" not in headers:
            headers["User-Agent"] = _USER_AGENT
            kwargs["headers"] = headers

        # Enforce timeout limits
        timeout = kwargs.get("timeout", _DEFAULT_TIMEOUT)
        if timeout is None or timeout > _MAX_TIMEOUT:
            kwargs["timeout"] = _MAX_TIMEOUT
        elif timeout <= 0:
            kwargs["timeout"] = _DEFAULT_TIMEOUT

        return kwargs

    def request(self, method: str, url: str, **kwargs) -> Any:
        """Send an HTTP request.

        Resolves once and connects to that exact IP without following redirects.
        """
        parsed, peer_ip = self._check_url(url)
        kwargs = self._ensure_headers(kwargs)

        logger.info(
            "SandboxedHTTP: %s %s %s (caller=%s)",
            method.upper(),
            url,
            f"scope={self._scope}",
            self._caller,
        )

        import json as _json
        timeout = kwargs.get("timeout", _DEFAULT_TIMEOUT)
        headers = kwargs.get("headers", {})
        data = kwargs.get("data")
        json_data = kwargs.get("json")

        if json_data is not None:
            data = _json.dumps(json_data).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")

        if isinstance(data, str):
            data = data.encode("utf-8")

        conn = None
        try:
            import http.client

            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            path = (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "")
            host_header = parsed.hostname
            if parsed.port and parsed.port != (443 if parsed.scheme == "https" else 80):
                host_header = f"{host_header}:{parsed.port}"
            if parsed.scheme == "https":
                class PinnedHTTPSConnection(http.client.HTTPSConnection):
                    def connect(inner) -> None:
                        sock = socket.create_connection((peer_ip, port), inner.timeout)
                        inner.sock = inner._context.wrap_socket(sock, server_hostname=parsed.hostname)
                conn = PinnedHTTPSConnection(parsed.hostname, port, timeout=timeout)
            else:
                conn = http.client.HTTPConnection(peer_ip, port, timeout=timeout)
            conn.putrequest(method.upper(), path, skip_host=True)
            conn.putheader("Host", host_header)
            for key, value in headers.items():
                if key.lower() != "host":
                    conn.putheader(key, value)
            conn.endheaders(data)
            resp = conn.getresponse()
            body = resp.read()
            return _SandboxResponse(
                status_code=resp.status,
                headers=dict(resp.headers),
                body=body,
            )
        except OSError as exc:
            raise SandboxHTTPError(f"リクエスト失敗: {exc}") from exc
        finally:
            if conn is not None:
                conn.close()

    def get(self, url: str, **kwargs) -> Any:
        """Send a GET request."""
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> Any:
        """Send a POST request."""
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs) -> Any:
        """Send a PUT request."""
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs) -> Any:
        """Send a DELETE request."""
        return self.request("DELETE", url, **kwargs)


class _SandboxResponse:
    """Response object for SandboxedHTTPClient."""

    def __init__(self, status_code: int, headers: dict, body: bytes) -> None:
        self.status_code = status_code
        self.headers = headers
        self._body = body

    @property
    def text(self) -> str:
        return self._body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        import json
        return json.loads(self._body)

    @property
    def content(self) -> bytes:
        return self._body

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 400
