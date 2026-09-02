"""HTTP client for Hailo remote tagger (Raspberry Pi endpoint)."""

import contextlib
import ipaddress
import json
import socket
import threading
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

# Serializes the process-global socket.getaddrinfo monkeypatch in
# pinned_dns below across concurrent requests.
_DNS_PIN_LOCK = threading.Lock()

_HAILO_BLOCKED_HOSTNAMES = frozenset({"metadata.google.internal", "metadata.goog"})


def _is_hailo_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return bool(ip.is_unspecified or ip.is_loopback or ip.is_link_local)


def resolve_hailo_host(hostname: str, port: int) -> list:
    """Resolve `hostname` exactly once and validate every returned address.

    Private LAN ranges are intentionally allowed (the Hailo Tagger targets a
    LAN device); only loopback/link-local/unspecified/metadata are blocked.
    Raises ValueError on failure. Returning the resolved addrinfo list lets
    the caller pin the connection via `pinned_dns` instead of letting
    urllib re-resolve later — two independent lookups a DNS-rebinding
    attacker could answer differently.
    """
    if hostname.lower() in _HAILO_BLOCKED_HOSTNAMES:
        raise ValueError("Blocked address")
    try:
        infos = socket.getaddrinfo(hostname, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"Cannot resolve host: {exc}") from None
    for _family, _type, _proto, _canonname, sockaddr in infos:
        try:
            ip = ipaddress.ip_address(str(sockaddr[0]).split("%", 1)[0])
        except ValueError:
            continue
        if _is_hailo_blocked_ip(ip):
            raise ValueError("Blocked address")
    return infos


@contextlib.contextmanager
def pinned_dns(hostname: str, infos: list):
    """Pin `socket.getaddrinfo(hostname, ...)` to already-validated `infos`
    for the duration of the block (closes the DNS-rebinding gap between
    validation and the actual connection). Process-global monkeypatch,
    serialized via `_DNS_PIN_LOCK`.
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


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse HTTP redirects so a validated endpoint can't be redirected to
    an internal/loopback address after the SSRF check has already passed."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "Redirects are not allowed", headers, fp)


# ProxyHandler({}) disables urllib's default proxy auto-detection (from
# http_proxy/https_proxy env vars or platform settings) — a proxy would
# resolve and connect to the target itself, silently bypassing the pinned
# address and reopening the DNS-rebinding/SSRF gap `pinned_dns` closes.
HAILO_NO_REDIRECT_OPENER = urllib.request.build_opener(
    _NoRedirectHandler, urllib.request.ProxyHandler({})
)


def call_hailo_tagger(
    image_path: str,
    endpoint_url: str,
    timeout: int = 30,
    bearer_token: str = "",
) -> list:
    """POST image to Hailo tagger endpoint.

    Args:
        bearer_token: If set, included as Authorization: Bearer header.

    Returns list of {"tag": str, "confidence": float} dicts.
    """
    parsed = urlparse(endpoint_url)
    hostname = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    infos = resolve_hailo_host(hostname, port)

    url = endpoint_url.rstrip("/") + "/tag"
    image_bytes = Path(image_path).read_bytes()
    suffix = Path(image_path).suffix.lower()
    mime_map = {
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
    }
    mime = mime_map.get(suffix, "image/jpeg")

    boundary = "----HailoTaggerBoundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="image{suffix}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode() + image_bytes + f"\r\n--{boundary}--\r\n".encode()

    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Accept": "application/json",
        "User-Agent": "YU-AI-Manager/1.0",
    }
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"

    req = urllib.request.Request(
        url, data=body, headers=headers, method="POST",
    )
    with pinned_dns(hostname, infos), HAILO_NO_REDIRECT_OPENER.open(req, timeout=timeout) as resp:
        result = json.loads(resp.read())
    return result.get("tags", [])
