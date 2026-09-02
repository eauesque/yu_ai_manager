"""Event bus handler for semantic search.

Subscribes to scan.complete to optionally auto-index new files.
Uses encoder_factory for backend-agnostic indexing.
"""

import logging
import threading

from core.event_bus import event_bus
from core.event_bus.event_types import SCAN_COMPLETE

logger = logging.getLogger(__name__)


def on_scan_complete(event) -> None:
    """Handle scan.complete: refresh helper table and optionally auto-index new files."""
    from core.extensions_core.extensions_admin import get_extension_config_value

    from core.services_core.clip_search_helper_service import (
        delete_clip_eligible_file_ids,
        mark_clip_eligible_clean,
        mark_clip_eligible_dirty,
        refresh_clip_eligible_files_table,
        sync_clip_eligible_file_ids,
    )

    auto_index = get_extension_config_value(
        "builtin-hailo-semantic-search", "auto_index_on_scan", False
    )
    added_count = event.data.get("added_count", 0)
    updated_count = event.data.get("updated_count", 0)
    deleted_count = event.data.get("deleted", 0)
    if added_count == 0 and updated_count == 0 and deleted_count == 0:
        return
    mark_clip_eligible_dirty()
    added_ids = event.data.get("added_ids") or []
    updated_ids = event.data.get("updated_ids") or []
    deleted_ids = event.data.get("deleted_ids") or []

    def _after_scan() -> None:
        try:
            changed_ids = list(dict.fromkeys([*added_ids, *updated_ids]))
            can_incremental = (
                added_count == len(added_ids)
                and updated_count == len(updated_ids)
                and deleted_count == len(deleted_ids)
                and bool(changed_ids or deleted_ids)
            )
            if can_incremental:
                if deleted_ids:
                    delete_clip_eligible_file_ids(deleted_ids)
                if changed_ids:
                    sync_clip_eligible_file_ids(changed_ids)
                mark_clip_eligible_clean()
            else:
                refresh_clip_eligible_files_table()
        except Exception:
            logger.warning("clip-search helper refresh after scan failed", exc_info=True)
            return

        if not auto_index or added_count == 0:
            return

        logger.info(
            "Scan complete with %d new files, starting auto-index", added_count
        )

        from .indexer import start_indexing

        start_indexing()

    threading.Thread(
        target=_after_scan,
        name="semantic-scan-refresh",
        daemon=True,
    ).start()


def subscribe_semantic_events() -> None:
    """Register semantic search event handlers on the global event bus."""
    event_bus.subscribe(SCAN_COMPLETE, on_scan_complete)
    logger.info("Semantic search event handlers registered")
