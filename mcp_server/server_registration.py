"""Registration helpers for MCP server assembly."""

from __future__ import annotations

import os

from .facade import (
    FACADE_SPECS,
    facade_enabled,
    hubs_absorbed_by_facades,
    register_facade,
    register_help_tool,
    reset_for_tests,
)
from .server_registration_manifest import (
    ENV_VAR,
    ToolRegistration,
    parse_profiles,
    selected_registrations,
)


def _register_direct(mcp, client, registrations: list[ToolRegistration]) -> None:
    for registration in registrations:
        registration.load()(mcp, client)


def register_all_tools(mcp, client):
    # server_tools (core) must be registered first, and is never absorbed by a
    # facade: it is the most-used surface, where an extra round trip costs most.
    from .server_tools import register_core_tools

    register_core_tools(mcp, client)

    registrations = selected_registrations(parse_profiles(os.environ.get(ENV_VAR)))

    if not facade_enabled():
        _register_direct(mcp, client, registrations)
        return

    reset_for_tests()
    by_module = {r.module_name: r for r in registrations}
    published = False
    for spec in FACADE_SPECS:
        selected = [by_module[hub] for hub in spec.hubs if hub in by_module]
        if selected:
            register_facade(mcp, client, spec, [r.load() for r in selected])
            published = True

    absorbed = hubs_absorbed_by_facades()
    _register_direct(
        mcp, client, [r for r in registrations if r.module_name not in absorbed]
    )

    # yu_help only describes facade actions; without a facade it describes nothing.
    if published:
        register_help_tool(mcp)
