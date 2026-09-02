# docs/templates/extension_blueprint/core_impl/_blueprint.py
"""Shared Blueprint instance for __EXTNAME__ extension."""
from __future__ import annotations

from quart import Blueprint

bp = Blueprint(
    "__EXTNAME__",
    __name__,
    template_folder="../templates",
)
