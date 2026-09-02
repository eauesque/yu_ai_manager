"""MD Viewer API blueprint factory facade."""

from __future__ import annotations

from quart import Blueprint, render_template

from .api_routes_files import register_file_routes
from .api_routes_scan import register_scan_routes
from .api_utils import int_param


def create_md_viewer_blueprint(import_name: str) -> Blueprint:
    """Create and return the Quart Blueprint for MD Viewer."""

    bp = Blueprint(
        "md_viewer",
        import_name,
        template_folder="templates",
    )

    # ── UI page ─────────────────────────────────────────────

    @bp.route("/")
    async def index():
        return await render_template("md_viewer/md_viewer.html")

    register_file_routes(bp, int_param)
    register_scan_routes(bp)
    return bp
