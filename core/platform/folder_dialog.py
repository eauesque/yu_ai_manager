"""OS-native folder selection dialog.

Windows: tkinter (in-process, fast) -> PowerShell FolderBrowserDialog fallback
macOS:   osascript (AppleScript)
Linux:   zenity -> tkinter fallback
"""

import subprocess
import threading

from .detect import CURRENT_OS, OSType


def _decode_output(raw: bytes | None) -> str:
    """Decode subprocess output (multi-encoding support)."""
    data = raw or b""
    if not data:
        return ""
    candidates = ["utf-8-sig"]
    if data.startswith((b"\xff\xfe", b"\xfe\xff")) or (b"\x00" in data):
        candidates.extend(["utf-16", "utf-16-le"])
    candidates.append("cp932")
    for enc in candidates:
        try:
            return data.decode(enc).strip()
        except Exception:  # noqa: S112 -- trying candidate encodings; a failure is how the loop advances
            continue
    return data.decode("utf-8", errors="replace").strip()


def _sanitize_path_for_dialog(path: str) -> str:
    """Normalize initial directory input without mangling valid path names."""
    if not path:
        return ""
    sanitized = path.replace("\x00", "")
    sanitized = sanitized.replace("\r", "").replace("\n", "")
    return sanitized.strip()


def select_folder(initial_dir: str = "") -> dict[str, str | None | bool]:
    """Open the OS-native folder selection dialog."""
    result: dict[str, str | None | bool] = {
        "path": None, "error": None, "cancelled": True,
    }

    def run_dialog():
        try:
            if CURRENT_OS is OSType.WINDOWS:
                _select_folder_windows(result, initial_dir)
                return
            if CURRENT_OS is OSType.MACOS:
                _select_folder_macos(result, initial_dir)
                return
            _select_folder_linux(result, initial_dir)
        except subprocess.TimeoutExpired:
            result["error"] = "タイムアウト"
            result["cancelled"] = False
        except Exception as e:
            result["error"] = str(e)
            result["cancelled"] = False

    t = threading.Thread(target=run_dialog)
    t.start()
    t.join(timeout=130)
    if t.is_alive():
        result["error"] = "タイムアウト"
        result["cancelled"] = False
    elif result.get("path") or result.get("error"):
        result["cancelled"] = False
    return result


def _select_folder_windows(result: dict, initial_dir: str) -> None:
    """Windows: prefer in-process tkinter (fast), fall back to PowerShell.

    PowerShell + ``Add-Type -AssemblyName System.Windows.Forms`` cold-start
    typically takes 1-3s before the dialog appears. tkinter runs in-process
    and opens in ~200-500ms, which is what the user feels as "responsive".
    """
    safe_dir = _sanitize_path_for_dialog(initial_dir) if initial_dir else ""
    if _select_folder_tk(result, safe_dir):
        return
    _select_folder_windows_powershell(result, safe_dir)


def _select_folder_tk(result: dict, initial_dir: str) -> bool:
    """Open tkinter folder dialog. Returns True if tk was usable.

    The path/cancel state is written to ``result``; True means "handled,
    don't fall through". False means tk could not run (no display, missing
    module) and the caller should try the platform-native fallback.
    """
    import contextlib

    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        return False
    try:
        root = tk.Tk()
    except Exception:
        return False
    try:
        root.withdraw()
        # Keep dialog on top of the main app window.
        with contextlib.suppress(Exception):
            root.attributes("-topmost", True)
        path = filedialog.askdirectory(
            initialdir=initial_dir or None,
            title="フォルダを選択",
            mustexist=True,
            parent=root,
        )
    finally:
        with contextlib.suppress(Exception):
            root.destroy()
    if path:
        result["path"] = path
        result["cancelled"] = False
    return True


def _select_folder_windows_powershell(result: dict, safe_dir: str) -> None:
    """Fallback: PowerShell FolderBrowserDialog (slower cold start)."""
    import os

    env = None
    ps_script = """
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = "scanするfolderを選択"
$dialog.ShowNewFolderButton = $false
"""
    if safe_dir:
        env = {**os.environ, "_YU_FOLDER_INIT": safe_dir}
        ps_script += '$dialog.SelectedPath = $env:_YU_FOLDER_INIT\n'
    ps_script += """
$result = $dialog.ShowDialog()
if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
    Write-Output $dialog.SelectedPath
}
"""
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        capture_output=True,
        timeout=120,
        env=env,
    )
    path = _decode_output(proc.stdout)
    if path:
        result["path"] = path
        result["cancelled"] = False


def _select_folder_macos(result: dict, initial_dir: str) -> None:
    """macOS: osascript (AppleScript)."""
    import os

    osa_script = (
        'set theFolder to POSIX path of'
        ' (choose folder with prompt "スキャンするフォルダを選択"'
    )
    if initial_dir:
        # Pass path safely via environment variable (prevent AppleScript injection)
        env = {**os.environ, "_YU_FOLDER_INIT": initial_dir}
        osa_script += (
            ' default location POSIX file'
            ' (system attribute "_YU_FOLDER_INIT")'
        )
    else:
        env = None
    osa_script += ")"
    proc = subprocess.run(
        ["osascript", "-e", osa_script],
        capture_output=True,
        timeout=120,
        env=env,
    )
    path = _decode_output(proc.stdout)
    if path:
        result["path"] = path.rstrip("/")
        result["cancelled"] = False
    elif proc.returncode == 1:
        result["cancelled"] = True


def _select_folder_linux(result: dict, initial_dir: str) -> None:
    """Linux: zenity with tkinter fallback."""
    try:
        proc = subprocess.run(
            ["zenity", "--file-selection", "--directory",
             "--title=フォルダを選択"],
            capture_output=True,
            timeout=120,
        )
        path = _decode_output(proc.stdout)
        if path:
            result["path"] = path
            result["cancelled"] = False
            return
    except FileNotFoundError:
        pass

    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        path = filedialog.askdirectory(
            initialdir=initial_dir or "/", title="フォルダを選択",
        )
        root.destroy()
        if path:
            result["path"] = path
            result["cancelled"] = False
    except Exception as e:
        result["error"] = f"ダイアログを開けません: {e}"
        result["cancelled"] = False
