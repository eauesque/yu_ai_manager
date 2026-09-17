"""ServiceRegistry registration of core services.

Called from runtime_runner.py at server startup.
"""

from __future__ import annotations

import logging

from .service_registry import ServiceRegistry
from .service_registry_core_services import register_core_services
from .service_registry_sandbox import (
    create_config_proxy,
    create_db_proxy,
    create_http_client,
    create_http_proxy,
)

logger = logging.getLogger(__name__)


def init_core_services(db_path=None) -> None:
    """Register core services with ServiceRegistry.

    Args:
        db_path: Path to the database file.
    """
    register_core_services(db_path=db_path)

    # Sandbox Proxy registration
    _init_sandbox_proxies()

    # http_client service registration (for SandboxedHTTPClient)
    ServiceRegistry.register("http_client", create_http_client)
    ServiceRegistry.register_sandbox("http_client", create_http_proxy)

    logger.info("ServiceRegistry: core services initialized (%d)", len(ServiceRegistry.names()))


def _init_sandbox_proxies() -> None:
    """Register Sandbox Proxy factories with ServiceRegistry."""
    ServiceRegistry.register_sandbox("db", create_db_proxy)
    ServiceRegistry.register_sandbox("config", create_config_proxy)
    logger.debug("ServiceRegistry: sandbox proxies registered")
