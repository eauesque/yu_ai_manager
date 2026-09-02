"""Migration 63: Composite index on file_annotations(source, key).

Speeds up annotation lookups that filter by ``source = ? AND key = ?``
without supplying a ``file_id``. The pre-existing UNIQUE(file_id, source, key)
index has ``file_id`` as the leading column, so it cannot be used for these
non-correlated lookups.

Concrete win: YOLO ``count_detected`` (Tool ページの hailo-yolo status) was
falling back to ``idx_annotations_key (key=?)`` and then post-filtering by
``source``. With this composite index it becomes a direct prefix match.
"""

import logging

from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)


def apply_migration_63(con) -> None:
    logger.info("  -> Migration 63: add idx_file_annotations_source_key")
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_file_annotations_source_key "
        "ON file_annotations(source, key)"
    )
    set_schema_version(con, 63, "Add composite index on file_annotations(source, key)")
