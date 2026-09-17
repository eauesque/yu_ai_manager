"""Group (folder/zip cluster) API service exports.

Builds responses for ``/api/groups-index``, ``/api/group-members``, and
``/api/container-thumb-ids``. Routes layer (``routes/files_routes_groups.py``)
stays thin and delegates here.

The underlying ``groups`` data structure lives in
``core/files_core/groups_index.py``; this module composes pure-sync response
builders on top of it.
"""

from core.group_api.responses import (
    build_container_thumb_ids_response,
    build_group_members_response,
    build_groups_index_response,
    build_groups_index_warm_response,
)

__all__ = [
    "build_container_thumb_ids_response",
    "build_group_members_response",
    "build_groups_index_response",
    "build_groups_index_warm_response",
]
