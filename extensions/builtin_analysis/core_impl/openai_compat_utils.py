"""OpenAI-compatible API connection utilities: URL validation, model listing, connection testing."""

import contextlib
import ipaddress
import json
import socket
import threading
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

# Serializes the process-global socket.getaddrinfo monkeypatch in
# _pinned_dns below across concurrent requests (see that function's
# docstring for why the patch itself is process-global).
_DNS_PIN_LOCK = threading.Lock()

# Hostnames known as cloud metadata endpoints
_BLOCKED_HOSTNAMES = frozenset({
    "metadata.google.internal",
    "metadata.goog",
})


def _is_blocked_address(hostname: str, *, allow_local: bool = False) -> bool:
    """Block access to metadata and optionally local/private addresses."""
    if hostname.lower() in _BLOCKED_HOSTNAMES:
        return True
    try:
        infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        return False
    for _family, _type, _proto, _canonname, sockaddr in infos:
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
        if (
            ip.is_link_local
            or ip.is_unspecified
            or (
                not allow_local
                and (
                    ip.is_loopback
                    or ip.is_private
                )
            )
        ):
            return True
    return False


def validate_openai_compat_url(url: str, *, allow_local: bool = False) -> str | None:
    """Validate an OpenAI-compatible server URL. Returns error message or None."""
    try:
        parsed = urlparse(url)
    except Exception:
        return "Invalid URL"

    if parsed.scheme not in ("http", "https"):
        return "Only http/https URLs are allowed"

    hostname = parsed.hostname or ""
    if not hostname:
        return "No hostname specified"

    if _is_blocked_address(hostname, allow_local=allow_local):
        return "Blocked address"

    return None


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse HTTP redirects so a validated base_url can't be redirected to
    an internal/loopback address after the SSRF check has already passed."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "Redirects are not allowed", headers, fp)


_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirectHandler)


def _resolve_and_check(hostname: str, port: int, *, allow_local: bool) -> list:
    """Resolve `hostname` exactly once and validate every returned address.

    Raises ValueError if the host can't be resolved or any resolved address
    is blocked. Returning the resolved addrinfo list lets the caller pin the
    connection to precisely what was validated (see `_pinned_dns`), instead
    of validating one DNS answer and then letting urllib re-resolve — two
    independent lookups a DNS-rebinding attacker can answer differently.
    """
    if hostname.lower() in _BLOCKED_HOSTNAMES:
        raise ValueError("Blocked address")
    try:
        infos = socket.getaddrinfo(hostname, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"Cannot resolve host: {exc}") from None
    for _family, _type, _proto, _canonname, sockaddr in infos:
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
        if ip.is_link_local or ip.is_unspecified or (
            not allow_local and (ip.is_loopback or ip.is_private)
        ):
            raise ValueError("Blocked address")
    return infos


@contextlib.contextmanager
def _pinned_dns(hostname: str, infos: list):
    """Force `socket.getaddrinfo(hostname, ...)` to return the already
    validated `infos` for the duration of the `with` block, so urllib's own
    connection-time DNS lookup can't be answered differently than what was
    just checked (DNS rebinding bypass of the SSRF guard). The patch is
    process-global, so concurrent pinned calls are serialized via
    `_DNS_PIN_LOCK` — acceptable since this is an infrequent admin-only path,
    not a hot one.
    """
    real_getaddrinfo = socket.getaddrinfo

    def _patched(host, *args, **kwargs):
        if host == hostname:
            return infos
        return real_getaddrinfo(host, *args, **kwargs)

    with _DNS_PIN_LOCK:
        socket.getaddrinfo = _patched
        try:
            yield
        finally:
            socket.getaddrinfo = real_getaddrinfo


def list_openai_compat_models(
    base_url: str, api_key: str = "", *, allow_local: bool = False
) -> list[dict[str, Any]]:
    """Fetch model list from OpenAI-compatible server via GET /v1/models.

    Raises ValueError if `base_url`'s host can't be resolved or resolves to
    a blocked address (metadata/link-local always; loopback/private unless
    `allow_local=True`).
    """
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http/https URLs are allowed")
    hostname = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    infos = _resolve_and_check(hostname, port, allow_local=allow_local)

    url = base_url.rstrip("/") + "/v1/models"
    headers: dict[str, str] = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, headers=headers)
    with _pinned_dns(hostname, infos), _NO_REDIRECT_OPENER.open(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    models = data.get("data", [])
    return [{"id": m.get("id", ""), "owned_by": m.get("owned_by", "")} for m in models]


def check_openai_compat_connection(
    base_url: str, api_key: str = "", *, allow_local: bool = False
) -> dict[str, Any]:
    """Test connection to OpenAI-compatible server. Returns status dict."""
    err = validate_openai_compat_url(base_url, allow_local=allow_local)
    if err:
        return {"connected": False, "models": [], "error": err}
    try:
        models = list_openai_compat_models(base_url, api_key, allow_local=allow_local)
        return {"connected": True, "models": models, "error": None}
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return {"connected": False, "models": [], "error": "Authentication failed (401)"}
        return {"connected": False, "models": [], "error": f"HTTP {e.code}"}
    except urllib.error.URLError as e:
        return {"connected": False, "models": [], "error": f"Cannot connect: {e.reason}"}
    except TimeoutError:
        return {"connected": False, "models": [], "error": "Connection timeout"}
    except Exception as e:
        return {"connected": False, "models": [], "error": str(e)}
