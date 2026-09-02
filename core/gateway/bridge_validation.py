"""URL validators for SD WebUI / ComfyUI gateway configurations."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

_RAW_SD_PORTS = {7860, 7861}
_RAW_COMFY_PORTS = {8188}
_LOOPBACK_HOSTS = {"localhost"}


def _validate_loopback_host(hostname: str | None) -> str | None:
    if not hostname:
        return "url must include a host"
    host = hostname.lower()
    if host in _LOOPBACK_HOSTS:
        return None
    try:
        if ipaddress.ip_address(host).is_loopback:
            return None
    except ValueError:
        pass
    return "host must be localhost or a loopback IP"


def validate_sd_gateway_url(url: str) -> str | None:
    """Return error string if url is an invalid SD gateway; None if OK or empty."""
    if not url:
        return None
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        return "scheme must be http or https"
    if err := _validate_loopback_host(p.hostname):
        return err
    port = p.port or (443 if p.scheme == "https" else 80)
    if port in _RAW_SD_PORTS:
        return f"raw SD port {port} — use gateway /sd prefix"
    path = p.path.rstrip("/")
    if path != "/sd" and not path.endswith("/sd"):
        return "url must end with /sd (gateway prefix)"
    return None


def validate_comfy_gateway_url(url: str) -> str | None:
    """Return error string if url is an invalid ComfyUI gateway; None if OK or empty."""
    if not url:
        return None
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        return "scheme must be http or https"
    if err := _validate_loopback_host(p.hostname):
        return err
    port = p.port or (443 if p.scheme == "https" else 80)
    if port in _RAW_COMFY_PORTS:
        return f"raw ComfyUI port {port} — use gateway /comfy prefix"
    path = p.path.rstrip("/")
    if path not in ("/comfy", "/comfy/api") and not path.endswith(("/comfy", "/comfy/api")):
        return "url must end with /comfy or /comfy/api"
    return None


def validate_comfy_ws_url(url: str) -> str | None:
    """Return error string if url is an invalid ComfyUI websocket gateway."""
    if not url:
        return None
    p = urlparse(url)
    if p.scheme not in ("ws", "wss"):
        return "scheme must be ws or wss"
    if err := _validate_loopback_host(p.hostname):
        return err
    port = p.port or (443 if p.scheme == "wss" else 80)
    if port in _RAW_COMFY_PORTS:
        return f"raw ComfyUI port {port} — use gateway /comfy/ws prefix"
    if p.path.rstrip("/") != "/comfy/ws":
        return "url must end with /comfy/ws"
    return None
