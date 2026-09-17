"""Freeze & Pull-back API: Quart Blueprint factory.

The extension entrypoint calls create_fpb_blueprint() to create
the Blueprint.
"""

from __future__ import annotations

import logging
import re

from quart import Blueprint, render_template

from core.files_core.media_video import check_ffmpeg

from .api_generate_routes import register_generate_routes
from .api_output_routes import register_output_routes
from .job_runner import cancel_job, get_job_status, start_render_job
from .sidecar import DEFAULT_OUTPUT_DIR, list_outputs

logger = logging.getLogger(__name__)

_SAFE_FILENAME = re.compile(r"^[a-zA-Z0-9_\-]+\.[a-zA-Z0-9]+$")


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def create_fpb_blueprint(import_name: str) -> Blueprint:
    """Create and return the Quart Blueprint for Freeze & Pull-back."""

    bp = Blueprint(
        "freeze_pullback",
        import_name,
        template_folder="templates",
    )

    @bp.route("/")
    async def index():
        return await render_template("freeze_pullback/freeze_pullback.html")

    register_generate_routes(
        bp,
        check_ffmpeg_fn=lambda: check_ffmpeg(),
        start_render_job_fn=lambda params: start_render_job(params),
        get_job_status_fn=lambda: get_job_status(),
        cancel_job_fn=lambda: cancel_job(),
        require_admin_scope=_require_admin_scope,
    )
    register_output_routes(
        bp,
        default_output_dir=DEFAULT_OUTPUT_DIR,
        safe_filename_pattern=_SAFE_FILENAME,
        list_outputs_fn=lambda: list_outputs(),
        require_admin_scope=_require_admin_scope,
    )
    return bp
