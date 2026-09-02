"""builtin-download Extension entrypoint."""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from quart import Blueprint, Response, request  # noqa: E402

from core.infra_core.api_errors import api_error  # noqa: E402

from .core_impl.batch_zip import build_batch_zip_filename, open_batch_zip_stream  # noqa: E402

_MAX_IDS = 500


def get_blueprint():
    bp = Blueprint("download", __name__)

    @bp.route("/batch-zip", methods=["POST"])
    async def api_batch_zip():
        """Download selected images as a ZIP archive."""
        data = await request.get_json(silent=True)
        if not isinstance(data, dict):
            return api_error("JSON object required", 400)

        file_ids = data.get("file_ids")
        if not isinstance(file_ids, list) or not file_ids:
            return api_error("file_ids (non-empty array) required", 400)

        try:
            file_ids = [int(x) for x in file_ids]
        except (TypeError, ValueError):
            return api_error("file_ids must be integers", 400)

        if len(file_ids) > _MAX_IDS:
            return api_error(f"Too many IDs (max {_MAX_IDS})", 400)

        from core.services_core.db_api import get_readonly_db
        con = get_readonly_db()
        zip_file, count = open_batch_zip_stream(con, file_ids)

        if count == 0:
            return api_error("No downloadable files found", 404)

        filename = build_batch_zip_filename()
        assert zip_file is not None

        def generate():
            try:
                while True:
                    chunk = zip_file.read(65536)
                    if not chunk:
                        break
                    yield chunk
            finally:
                zip_file.close()

        return Response(
            generate(),
            mimetype="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return bp


__all__ = ["get_blueprint"]
