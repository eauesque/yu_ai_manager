import logging

logger = logging.getLogger(__name__)
"""Tag normalization hook during scan.

Calls the on_normalize_tags (chain) hook,
allowing extensions to transform tags.
"""



def normalize_via_hooks(tag: str) -> str:
    """Transform tags via the extension's on_normalize_tags hook.

    Returns as-is if no hook is registered.
    """
    from .scanner_state import _extension_manager

    if _extension_manager is None:
        return tag
    try:
        result = _extension_manager.invoke_hook("on_normalize_tags", tag)
        if result is not None and isinstance(result, str):
            return result
    except Exception:
        logger.debug("scan step failed", exc_info=True)
    return tag
