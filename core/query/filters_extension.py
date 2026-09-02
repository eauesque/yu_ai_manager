"""Extension filter application.

Invokes the on_search_filter (chain) hook, allowing
extensions to add WHERE conditions to the query.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def apply_extension_filters(
    where_parts: list[str],
    params: list[Any],
) -> None:
    """Add WHERE conditions via the on_search_filter hook.

    The hook receives {"where_parts": [...], "params": [...]} as a dict.
    Extensions modify and return where_parts and params (chain mode).

    Note: To prevent SQL injection, extensions must use ? placeholders only.
    """
    try:
        from core.scan_core.scanner_state import _extension_manager
        if _extension_manager is None:
            return

        filter_data: dict[str, Any] = {
            "where_parts": where_parts,
            "params": params,
        }
        result = _extension_manager.invoke_hook("on_search_filter", filter_data)
        if result is not None and isinstance(result, dict):
            # Apply the new lists returned by the Extension
            new_where = result.get("where_parts")
            new_params = result.get("params")
            if isinstance(new_where, list) and isinstance(new_params, list):
                where_parts.clear()
                where_parts.extend(new_where)
                params.clear()
                params.extend(new_params)
    except Exception:
        logger.warning("step failed", exc_info=True)
