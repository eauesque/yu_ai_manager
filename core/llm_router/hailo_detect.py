"""Hailo LLM local detection for auto-registration.

Pure functions used by runtime_subsystems.init_llm_router_discovery at
startup. Does NOT mutate BackendCatalog — returns a HailoDetectionResult
dataclass that the caller converts into BackendInfo objects.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import httpx

logger = logging.getLogger("core.llm_router.hailo_detect")

# Hailo device node paths we consider valid evidence of an attached NPU.
# HailoRT's standard naming is /dev/hailo0, but Raspberry Pi 5 with the AI HAT
# exposes the device as /dev/h1x-0 (confirmed on pi2, HailoRT 5.3.0).
# Both are accepted so the same detection works across platforms.
_HAILO_DEVICE_PATHS: tuple[str, ...] = ("/dev/hailo0", "/dev/h1x-0")


@dataclass(frozen=True)
class HailoDetectionResult:
    """What Phase A found on this host. All fields None / False on non-Hailo hosts."""
    yu_extension_available: bool
    hailo_ollama_base_url: str | None
    device_count: int = 1


def detect_yu_extension_hailo_llm() -> bool:
    """Can this yu instance serve Hailo LLM via the builtin-hailo-genai extension?

    Safe on non-Hailo hosts: import failures and missing device node both
    return False cleanly. This runs at startup on every platform, including
    Windows/macOS developer machines that do not have core.hailo_device_core
    installed at all.

    Device node presence is the primary signal. The ``hailo_platform.genai``
    import check is attempted as a bonus but is NOT required: on Pi5 the
    package is often installed system-wide (not in our uv venv), yet the
    builtin-hailo-genai extension still loads correctly via our own import
    hooks. Requiring the import caused false-negative detection on Pi5 —
    capabilities:[] in mDNS even when the extension was fully functional.
    """
    if not any(Path(p).exists() for p in _HAILO_DEVICE_PATHS):
        return False
    try:
        from core.hailo_device_core.device_manager import is_genai_available
        if is_genai_available():
            return True
    except Exception:
        logger.warning("step failed", exc_info=True)
    # Device node exists but hailo_platform not importable in this venv
    # (e.g. installed system-wide on Pi5). Trust the device node.
    return True


def count_hailo_devices() -> int:
    """Return the number of Hailo device nodes detected on this host.

    Returns 0 on non-Hailo hosts. Safe to call on any platform.
    """
    try:
        from core.hailo_device_core.device_manager import list_device_paths
        return len(list_device_paths())
    except ImportError:
        return 0


async def detect_local_hailo_ollama(
    port: int = 8000,
    timeout_sec: float = 2.0,
) -> str | None:
    """Probe localhost:<port>/v1/models to detect a running hailo-ollama.

    Exception scope: ``httpx.RequestError`` is the base of all network-layer
    errors (``ConnectError`` for port-closed, ``TimeoutException`` for
    timeout, ``NetworkError`` for DNS/socket issues, etc.). ``ValueError``
    catches the JSON decoder (``json.JSONDecodeError`` is a ValueError
    subclass). We do NOT catch ``httpx.HTTPStatusError`` because we are not
    calling ``raise_for_status()`` — non-200 responses are handled
    explicitly via ``resp.status_code != 200``.
    """
    url = f"http://localhost:{port}/v1/models"
    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            body = resp.json()
            if not isinstance(body, dict) or "data" not in body:
                return None
    except (httpx.RequestError, ValueError):
        return None
    return f"http://localhost:{port}/v1"


async def detect_all(
    *,
    self_web_port: int,
    hailo_ollama_enabled: bool = True,
    hailo_ollama_port: int = 8000,
    existing_backend_urls: frozenset[str] = frozenset(),
) -> HailoDetectionResult:
    """Unified detection entry point.

    self_web_port is REQUIRED so we can refuse to probe our own listening
    port (prevents a mis-configured yu from registering itself as a
    hailo-ollama backend — see spec §6.1).

    existing_backend_urls: set of base_urls already registered via
    config.llm_router.backends. If a hailo-ollama entry is already
    configured, we skip the probe (user intent takes precedence).
    """
    yu_ext = detect_yu_extension_hailo_llm()
    device_count = count_hailo_devices()

    hailo_ollama_url: str | None = None
    if hailo_ollama_enabled and hailo_ollama_port != self_web_port:
        probe_candidate = f"http://localhost:{hailo_ollama_port}/v1"
        if probe_candidate not in existing_backend_urls:
            hailo_ollama_url = await detect_local_hailo_ollama(hailo_ollama_port)

    return HailoDetectionResult(
        yu_extension_available=yu_ext,
        hailo_ollama_base_url=hailo_ollama_url,
        device_count=max(device_count, 1) if yu_ext else device_count,
    )
