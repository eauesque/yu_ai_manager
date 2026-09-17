"""Sandbox proxy builders for ServiceRegistry bootstrap."""

from __future__ import annotations


def create_db_proxy(real_db_fn, caller_name: str):
    """Create a Sandbox Proxy for the db service."""
    from core.extensions_core.sandbox.sandbox_proxy import SandboxedDB
    from core.extensions_core.token_mgmt.capability_token import get_enforcer

    enforcer = get_enforcer()
    can_write = enforcer.has_permission(caller_name, "db:write")

    return SandboxedDB(real_db_fn, caller_name, can_write)


def create_http_client():
    """Default factory for the http_client service (unrestricted)."""
    from core.extensions_core.sandbox.sandbox_http import SandboxedHTTPClient

    return SandboxedHTTPClient("core", scope="internet")


def create_http_proxy(real_client, caller_name: str):
    """Create a Sandbox Proxy for the http_client service."""
    from core.extensions_core.sandbox.sandbox_http import SandboxedHTTPClient
    from core.extensions_core.token_mgmt.capability_token import get_enforcer

    enforcer = get_enforcer()

    if enforcer.has_permission(caller_name, "network:internet"):
        scope = "internet"
    elif enforcer.has_permission(caller_name, "network:local"):
        scope = "local"
    else:
        scope = None

    return SandboxedHTTPClient(caller_name, scope=scope)


def create_config_proxy(real_config_fn, caller_name: str):
    """Create a Sandbox Proxy for the config service."""
    from core.extensions_core.token_mgmt.capability_token import get_enforcer

    enforcer = get_enforcer()
    can_write = enforcer.has_permission(caller_name, "config:write")

    if can_write:
        return real_config_fn

    def readonly_config_fn():
        config = real_config_fn()
        if isinstance(config, dict):
            import copy

            return copy.deepcopy(config)
        return config

    return readonly_config_fn
