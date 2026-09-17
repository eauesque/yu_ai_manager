"""Additional route groups for the Prompt Library blueprint."""

from __future__ import annotations

from collections.abc import Callable

from quart import Blueprint

from .prompt_library_api_routes_bulk import register_bulk_routes
from .prompt_library_api_routes_folders import register_folder_routes
from .prompt_library_api_routes_from_file import register_from_file_routes
from .prompt_library_api_routes_tags import register_tag_routes


def register_extra_routes(bp: Blueprint, require_admin_scope: Callable[[], object | None] | None = None) -> None:
    """Register extra Prompt Library routes on *bp*."""
    register_folder_routes(bp, require_admin_scope=require_admin_scope)
    register_tag_routes(bp, require_admin_scope=require_admin_scope)
    register_from_file_routes(bp, require_admin_scope=require_admin_scope)
    register_bulk_routes(bp, require_admin_scope=require_admin_scope)
