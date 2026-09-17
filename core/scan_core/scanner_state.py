"""Shared scanner runtime state (extension manager hook)."""


_extension_manager = None


def set_extension_manager(mgr):
    global _extension_manager
    _extension_manager = mgr


def try_extension_parsers(filepath: str, raw_meta: str | None, chunks: dict[str, str]):
    if _extension_manager is None:
        return None
    try:
        return _extension_manager.invoke_hook("on_scan_file", filepath, raw_meta, chunks)
    except Exception:
        return None
