"""File API blueprint wiring.

Single-file handlers live in ``files_routes.py``.
Grouped and batch endpoints are split into dedicated route modules.
"""

from quart import Blueprint

from routes import files_routes as _single
from routes import files_routes_batch as _batch
from routes import files_routes_groups as _groups

bp = Blueprint("files", __name__)

# Wire up routes to handler functions
bp.add_url_rule("/api/thumbnail/<int:file_id>", view_func=_single.thumbnail)
bp.add_url_rule("/api/file/<int:file_id>", view_func=_single.file_detail)
bp.add_url_rule("/_internal/file/detail/<int:file_id>", view_func=_single.internal_file_detail)
bp.add_url_rule("/api/convert", view_func=_single.convert, methods=["POST"])
bp.add_url_rule("/api/preview/<int:file_id>", view_func=_single.preview)
bp.add_url_rule("/api/original/<int:file_id>", view_func=_single.original)
bp.add_url_rule("/api/groups-index", view_func=_groups.groups_index)
bp.add_url_rule("/api/groups-index/warm", view_func=_groups.groups_index_warm)
bp.add_url_rule("/api/group-members", view_func=_groups.group_members)
bp.add_url_rule("/api/thumbnails/batch", view_func=_batch.thumbnails_batch, methods=["POST"])
bp.add_url_rule("/api/thumbnails/warmup", view_func=_batch.thumbnails_warmup, methods=["POST"])
bp.add_url_rule("/api/container-thumb-ids", view_func=_groups.container_thumb_ids)
