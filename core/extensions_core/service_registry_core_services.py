"""Core service registrations for ServiceRegistry bootstrap."""

from __future__ import annotations

import logging

from .service_registry import ServiceRegistry

logger = logging.getLogger(__name__)


def register_core_services(*, db_path=None) -> None:
    """Register core services that extensions may access."""
    from core.services_core.db_state import get_db

    ServiceRegistry.register("db", get_db)

    if db_path is not None:
        ServiceRegistry.register("db_path", db_path)

    from core.services_core.db_api import get_config

    ServiceRegistry.register("config", get_config)

    from core import event_bus

    ServiceRegistry.register("event_bus", event_bus)

    try:
        from core.jobs_core import job_manager

        ServiceRegistry.register("job_manager", job_manager)
    except ImportError:
        logger.debug("job_manager not available")

    try:
        from importlib import import_module
        _fav_mod = import_module("extensions.builtin_favorites_manager.core_impl")
        _fav_export = import_module("extensions.builtin_favorites_manager.core_impl.favorites_export")

        ServiceRegistry.register("favorites.list_collections", _fav_mod.list_collections)
        ServiceRegistry.register("favorites.list_favorites", _fav_mod.list_favorites)
        ServiceRegistry.register("favorites.export_zip_bytes", _fav_export.export_favorites_zip_bytes)
    except ImportError:
        logger.debug("favorites_core not available for ServiceRegistry")

    try:
        from importlib import import_module
        _trophy_judge = import_module("extensions.builtin_trophy.core_impl.trophy_judge")
        judge_all = _trophy_judge.judge_all

        ServiceRegistry.register("trophies.judge_all", judge_all)
    except ImportError:
        logger.debug("trophy_core not available for ServiceRegistry")
