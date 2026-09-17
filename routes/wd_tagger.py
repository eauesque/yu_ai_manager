"""WD-Tagger API routes facade.

Endpoints for WD-Tagger Danbooru auto-tagging:
config, single/batch tagging, tag CRUD, model management, XMP.
"""

import logging
from importlib import import_module

from quart import Blueprint

from routes.wd_tagger_admin_routes import register_admin_routes
from routes.wd_tagger_batch_routes import register_batch_routes
from routes.wd_tagger_config_routes import register_config_routes
from routes.wd_tagger_retag_routes import register_retag_routes
from routes.wd_tagger_tag_routes import register_tag_routes


def _wt(module_name: str):
    """Import a module from the WD-Tagger extension core_impl package."""
    return import_module(
        f"extensions.builtin_wd_tagger.core_impl.{module_name}"
    )


bp = Blueprint("wd_tagger", __name__)
logger = logging.getLogger(__name__)


from core.web.auth_helpers import require_admin_scope as _require_admin_scope

register_config_routes(bp, _wt, _require_admin_scope, logger)
register_tag_routes(bp, _wt, _require_admin_scope, logger)
register_batch_routes(bp, _wt, _require_admin_scope, logger)
register_retag_routes(bp, _require_admin_scope, logger)
register_admin_routes(bp, _wt, _require_admin_scope, logger)
