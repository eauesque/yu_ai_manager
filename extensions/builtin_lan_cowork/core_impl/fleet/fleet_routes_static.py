"""Static asset route for fleet UI."""
from __future__ import annotations

import os


def register_fleet_static_routes(bp) -> None:
    @bp.route("/fleet/static/<path:filename>")
    async def fleet_static(filename):
        from quart import send_from_directory

        static_dir = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "ui", "fleet")
        )
        return await send_from_directory(static_dir, filename)
