"""Invoke helpers for extension hook registry."""

import logging
from typing import Any

logger = logging.getLogger(__name__)

from core.extensions_core.extensions_defs import HookEntry


def invoke_exclusive(entries: list[HookEntry], *args, **kwargs) -> Any:
    for entry in entries:
        try:
            result = entry.callback(*args, **kwargs)
            if result is not None:
                return result
        except Exception as e:
            logger.error(f"Hook error in {entry.extension_name}: {e}", exc_info=True)
    return None


def invoke_chain(entries: list[HookEntry], *args, **kwargs) -> Any:
    if not args:
        return None

    current = args[0]
    rest_args = args[1:]

    for entry in entries:
        try:
            result = entry.callback(current, *rest_args, **kwargs)
            if result is not None:
                current = result
        except Exception as e:
            logger.error(f"Chain error in {entry.extension_name}: {e}", exc_info=True)

    return current


def invoke_collect(entries: list[HookEntry], *args, **kwargs) -> list[Any]:
    """Run each entry independently; concatenate non-None list results.

    Each entry receives identical (args, kwargs). Single non-list values
    are appended with a logger.warning (signature deviation).
    Exceptions from individual entries are logged and skipped; other
    entries' results are preserved.
    """
    results: list[Any] = []
    for entry in entries:
        try:
            r = entry.callback(*args, **kwargs)
        except Exception as e:
            logger.error(f"Collect error in {entry.extension_name}: {e}", exc_info=True)
            continue
        if r is None:
            continue
        if isinstance(r, list):
            results.extend(r)
        else:
            logger.warning(
                f"{entry.extension_name}: collect hook returned non-list "
                f"({type(r).__name__}); appending as single item"
            )
            results.append(r)
    return results
