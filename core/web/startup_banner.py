"""Startup banner and LAN URL helpers."""

import logging
import socket
from pathlib import Path

logger = logging.getLogger(__name__)


def get_lan_ips() -> list:
    ips = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                ips.append(ip)
        ips = list(dict.fromkeys(ips))
    except Exception as exc:
        logger.debug("Failed to get LAN IPs via getaddrinfo: %s", exc)
    if ips:
        return ips
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return [ip]
    except Exception:
        return ["(IP取得失敗)"]


def print_startup_banner(db_path: Path, host: str, port: int, effective_pin: str | None,
                         *, profile_name: str | None = None, profiles: dict | None = None) -> None:
    is_lan = host in ("0.0.0.0", "::")
    logger.info("Starting web UI...")
    logger.info(f"  Database: {db_path}")
    if profile_name and profiles:
        label = profiles.get(profile_name, {}).get("label", profile_name)
        logger.info(f"  Profile: {profile_name} ({label})")

    if is_lan:
        logger.info("")
        logger.info("  +----------------------------------------------+")
        logger.info("  |  [!] LAN public mode                         |")
        logger.info("  |  Accessible from all devices on this network |")
        if effective_pin:
            logger.info("  |  [*] PIN auth: enabled                       |")
        else:
            logger.info("  |  [ ] PIN auth: disabled (use --pin to set)   |")
        logger.info("  +----------------------------------------------+")
        logger.info("")
        logger.info("  Access URL:")
        logger.info(f"    Local:     http://localhost:{port}")
        for ip in get_lan_ips():
            logger.info(f"    LAN:       http://{ip}:{port}")
    else:
        logger.info(f"  http://{host}:{port}")
