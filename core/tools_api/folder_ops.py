"""Folder browser helpers for tools routes."""

import os
import platform

from core.infra_core.debug_log import dlog
from core.tools.fs import list_dirs_payload, select_folder_dialog
from core.web.auth_restart import is_local_request_from


def _has_gui_display() -> bool:
    """Return False when no GUI display is available (headless Linux/WSL2)."""
    if platform.system() != "Linux":
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def select_folder_payload(initial_dir: str, origin: dict):
    """Build payload for native folder picker endpoint.

    `origin` must be obtained via `snapshot_request_origin()` from inside a
    request handler — this function may run in an executor thread where the
    Quart request proxy is unavailable.
    """
    remote_addr = origin.get("remote_addr", "")
    dlog(
        "tools",
        "select_folder.start",
        remote_addr=remote_addr,
        initial_dir=initial_dir,
    )

    if not is_local_request_from(origin):
        dlog("tools", "select_folder.blocked_remote", remote_addr=remote_addr)
        return {
            "path": None,
            "error": "remote_client_no_gui",
            "cancelled": False,
            "message": "リモートアクセス時はネイティブフォルダダイアログを使用できません。サーバーフォルダー参照を使ってください。",
        }, 200

    if not _has_gui_display():
        dlog("tools", "select_folder.headless")
        return {
            "path": None,
            "error": "headless_unsupported",
            "cancelled": False,
            "message": "ディスプレイが検出されません。サーバーフォルダー参照を使ってください。",
        }, 200

    result = select_folder_dialog(initial_dir)
    if result.get("error"):
        dlog("tools", "select_folder.done_error", error=result["error"])
    else:
        dlog("tools", "select_folder.done_ok", path=result.get("path"))
    return result, 200


def list_dirs_request_payload(raw_path: str, origin: dict):
    """Build payload for server directory listing endpoint.

    `origin` must be obtained via `snapshot_request_origin()` from inside a
    request handler — this function may run in an executor thread where the
    Quart request proxy is unavailable.
    """
    if not is_local_request_from(origin):
        return {"error": "Directory listing is only available from localhost"}, 403

    remote_addr = origin.get("remote_addr", "")
    dlog("tools", "list_dirs.start", raw_path=raw_path, remote_addr=remote_addr)
    payload, status = list_dirs_payload(raw_path)
    if status == 200:
        dlog("tools", "list_dirs.ok", current=payload.get("current"), roots=payload.get("roots"))
    return payload, status
