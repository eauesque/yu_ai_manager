"""Lightweight Service Locator.

Dependency injection point for extensions to access core services.
Enables mock replacement during tests.

Usage::

    from core.extensions_core.service_registry import ServiceRegistry

    # Register (at startup)
    ServiceRegistry.register("db", get_db)
    ServiceRegistry.register("event_bus", event_bus_module)

    # Retrieve (from extension)
    db = ServiceRegistry.get("db")

    # Factory registration (lazy initialization)
    ServiceRegistry.register_factory("heavy_service", lambda: create_heavy())

    # Retrieve with Sandbox Proxy (from L1/L2 extensions)
    db = ServiceRegistry.get("db", caller="my-extension")
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from .service_registry_access import apply_sandbox_hook

logger = logging.getLogger(__name__)


class ServiceRegistry:
    """Singleton Service Locator.

    Class methods only. No instantiation needed.
    """

    _services: dict[str, Any] = {}
    _factories: dict[str, Callable[[], Any]] = {}
    _sandbox_hooks: dict[str, Callable] = {}

    @classmethod
    def register(cls, name: str, service: Any) -> None:
        """Register a service by name."""
        cls._services[name] = service
        logger.debug("ServiceRegistry: registered '%s'", name)

    @classmethod
    def register_factory(cls, name: str, factory: Callable[[], Any]) -> None:
        """Register a lazy-initialization factory. Instantiated on first get() call."""
        cls._factories[name] = factory
        logger.debug("ServiceRegistry: registered factory '%s'", name)

    @classmethod
    def register_sandbox(cls, name: str, proxy_factory: Callable) -> None:
        """Register a Sandbox Proxy factory.

        Args:
            name: Service name (e.g., "db", "config")
            proxy_factory: Function returning (service, caller_name) -> sandboxed_service
        """
        cls._sandbox_hooks[name] = proxy_factory
        logger.debug("ServiceRegistry: registered sandbox for '%s'", name)

    @classmethod
    def get(cls, name: str, default: Any = None, *, caller: str = "") -> Any:
        """Get a service by name.

        When caller is specified, returns the service via Sandbox Proxy.
        When caller is not specified (legacy compatibility), returns as-is.

        Registered -> returns as-is.
        Factory -> instantiated on first call, cached thereafter.
        Unregistered -> returns default.
        """
        service = cls._resolve(name, default)
        if service is default or not caller:
            return service
        return cls._apply_sandbox(name, service, caller)

    @classmethod
    def _resolve(cls, name: str, default: Any) -> Any:
        """Resolve a service (internal)."""
        if name in cls._services:
            return cls._services[name]
        if name in cls._factories:
            service = cls._factories[name]()
            cls._services[name] = service
            del cls._factories[name]
            logger.debug("ServiceRegistry: factory '%s' -> instance", name)
            return service
        return default

    @classmethod
    def _apply_sandbox(cls, name: str, service: Any, caller: str) -> Any:
        """Apply Sandbox Proxy (internal).

        Bypasses L0 (TRUSTED) callers.
        Notifies RevocationTracker of access.
        """
        return apply_sandbox_hook(name, service, caller, cls._sandbox_hooks.get(name))

    @classmethod
    def has(cls, name: str) -> bool:
        """Check whether a service or factory is registered."""
        return name in cls._services or name in cls._factories

    @classmethod
    def names(cls) -> list[str]:
        """Return a list of registered service names."""
        return sorted(set(cls._services) | set(cls._factories))

    @classmethod
    def reset(cls) -> None:
        """Clear all registrations. For testing."""
        cls._services.clear()
        cls._factories.clear()
        cls._sandbox_hooks.clear()
        logger.debug("ServiceRegistry: reset")
