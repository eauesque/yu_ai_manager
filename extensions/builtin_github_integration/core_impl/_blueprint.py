"""Shared Blueprint instance for GitHub Integration.

All API sub-modules import ``bp`` from here to avoid circular imports.
"""

from __future__ import annotations

from quart import Blueprint

bp = Blueprint(
    "github_integration", __name__,
    template_folder="../templates",
)
