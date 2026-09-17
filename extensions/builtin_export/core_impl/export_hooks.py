"""Hook invocation during export.

Calls the on_export_record (chain) hook,
allowing Extensions to modify export records.
"""

import contextlib
from typing import Any


def apply_export_hooks(record: dict[str, Any]) -> dict[str, Any]:
    """Process a record through the on_export_record hook.

    フックが登録されていない場合はそのまま返す。
    エクスポートパイプラインの各レコードに対して呼び出す。
    """
    # A probe: no extension manager, no hook to invoke.
    with contextlib.suppress(Exception):
        from core.scan_core.scanner_state import _extension_manager
        if _extension_manager is None:
            return record
        result = _extension_manager.invoke_hook("on_export_record", record)
        if result is not None and isinstance(result, dict):
            return result
    return record
