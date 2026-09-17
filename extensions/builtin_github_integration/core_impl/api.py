"""GitHub Integration API routes -- hub module.

Defines the WebUI page route and imports all sub-modules so their
routes are registered on the shared Blueprint.
External code should only need ``from .api import bp``.
"""

from __future__ import annotations

import logging

from quart import render_template

# Re-export the shared blueprint for backward compatibility
from ._blueprint import bp  # noqa: F401

logger = logging.getLogger(__name__)


# ── WebUI Page ─────────────────────────────────────────────────

@bp.route("/ext/github")
async def github_page():
    """Main GitHub Integration WebUI."""
    return await render_template("github.html")


# ── Register sub-module routes on the shared blueprint ─────────
# Each sub-module imports ``bp`` from ``_blueprint`` and decorates routes.
# Importing them here triggers the route registration.

from . import api_accounts as _accounts  # noqa: F401,E402
from . import api_issues as _issues  # noqa: F401,E402
from . import api_queue as _queue  # noqa: F401,E402
from . import api_repos as _repos  # noqa: F401,E402
