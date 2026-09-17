"""macOS firewall pre-flight guard for LAN startup."""

from __future__ import annotations

import logging
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SOCKETFILTERFW = "/usr/libexec/ApplicationFirewall/socketfilterfw"
_LEGACY_STAMP_PATH = _PROJECT_ROOT / ".uv_fw_cdhash"


def _stamp_path_for(resolved_exe: str) -> Path:
    """One stamp per resolved listener path.

    The caller MUST pass an already-`os.path.realpath`-resolved string, the
    same way every other operation in this module (`_read_cdhash`,
    `_is_app_permitted`, `--add`/`--remove`/`--unblockapp`) is keyed on the
    resolved path, not the caller's raw spelling -- otherwise the same
    on-disk binary reached through a symlink or a `./`-prefixed path collides
    with itself under two different stamps (measured: a symlink and its
    realpath target hash to two different digests when the raw path is used).
    A shared stamp across *different* listeners would make Python and
    yu-server invalidate each other on every alternating launch; that part
    of the original rationale still holds.
    """
    import hashlib

    digest = hashlib.sha256(resolved_exe.encode("utf-8")).hexdigest()[:16]
    return _PROJECT_ROOT / f".uv_fw_cdhash.{digest}"


def _migrate_legacy_stamp(resolved_exe: str, stamp_path: Path) -> None:
    """Carry the pre-split single stamp forward, for Python only.

    Before the per-listener split, every macOS user (fast mode or not) had
    exactly one stamp: `.uv_fw_cdhash`, always naming the uv-managed Python.
    Without this, a user who never touches fast mode loses that stamp the
    moment this change ships and is forced through one unwanted sudo
    re-authentication on their next `--lan` launch (acceptance 17: a user who
    never opts into fast mode must see no change).

    Restricted to the exact case the legacy stamp is valid for: the resolved
    listener IS the running interpreter. Migrating it for any other listener
    (e.g. yu-server) would hand it a Python signature it never earned, which
    is the same bug the per-listener split exists to prevent.
    """
    if stamp_path.exists() or not _LEGACY_STAMP_PATH.exists():
        return
    if resolved_exe != os.path.realpath(sys.executable):
        return
    try:
        legacy = _LEGACY_STAMP_PATH.read_text(encoding="utf-8")
    except OSError:
        return
    try:
        stamp_path.write_text(legacy, encoding="utf-8")
    except OSError as exc:
        logger.warning("[FIREWALL] failed to migrate legacy firewall stamp: %s", exc)


def _read_cdhash(listener_exe: str) -> str | None:
    try:
        result = subprocess.run(
            ["codesign", "-d", "--verbose=4", listener_exe],
            capture_output=True,
            check=False,
            text=True,
        )
    except (FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    output = (result.stdout or "") + (result.stderr or "")
    match = re.search(r"^CDHash=([0-9a-f]+)", output, re.MULTILINE)
    if match is None:
        return None
    return match.group(1)


def _run_sudo(args: list[str]) -> bool:
    try:
        result = subprocess.run(args, check=False)
    except (FileNotFoundError, OSError) as exc:
        logger.error("[FIREWALL] command failed: %s", exc)
        return False
    return result.returncode == 0


def _is_app_permitted(listener_exe: str) -> bool | None:
    """Query the firewall for the app's allow state.

    Returns True if permitted, False if blocked, None if the state cannot be
    determined (socketfilterfw missing, error, or unrecognized output).
    """
    try:
        result = subprocess.run(
            [_SOCKETFILTERFW, "--getappblocked", listener_exe],
            capture_output=True,
            check=False,
            text=True,
        )
    except (FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    out = ((result.stdout or "") + (result.stderr or "")).lower()
    if "permitted" in out:
        return True
    if "blocked" in out:
        return False
    return None


def _is_interactive() -> bool:
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        return False


def ensure_lan_firewall_exception(listener_exe: str) -> bool:
    """Pre-authorise the process that will listen, whatever it is.

    Previously this only ever received the uv-managed Python. Fast mode
    replaces the listener with yu-server, and a stamp naming the old
    interpreter would leave `--lan` silently blocked.

    Returns True when the firewall exception is in place or unnecessary
    (non-macOS); returns False when startup should be aborted because the
    exception could not be (re)applied.
    """
    if platform.system() != "Darwin":
        return True

    resolved = os.path.realpath(listener_exe)
    stamp_path = _stamp_path_for(resolved)
    _migrate_legacy_stamp(resolved, stamp_path)
    cdhash = _read_cdhash(resolved)
    if cdhash is not None and stamp_path.exists():
        try:
            stamp = stamp_path.read_text(encoding="utf-8").strip()
        except OSError:
            stamp = None
        if stamp == cdhash and _is_app_permitted(resolved) is True:
            return True

    logger.info(
        "[FIREWALL] the listener's signature changed (or first run); updating "
        "macOS firewall exception. sudo password may be required."
    )
    logger.info(
        "[FIREWALL] 待受プロセスの署名が変更されたか初回起動です。"
        "macOSファイアウォール許可を更新します。"
        "sudoパスワードが必要な場合があります。"
    )

    interactive = _is_interactive()
    sudo_prefix = ["sudo"] if interactive else ["sudo", "-n"]
    if not _run_sudo(sudo_prefix + ["-v"]):
        if interactive:
            logger.error(
                "[FIREWALL] sudo authentication failed; aborting LAN startup."
            )
            logger.error("[FIREWALL] sudo認証に失敗しました。LAN起動を中止します。")
            return False
        logger.warning(
            "[FIREWALL] Non-interactive startup; cannot refresh the macOS "
            "firewall exception automatically. LAN clients may be unable to "
            "reach this server until you run socketfilterfw manually (or "
            "configure sudoers NOPASSWD)."
        )
        logger.warning(
            "[FIREWALL] 非対話起動のためファイアウォール許可を自動更新できません。"
            "別マシンから接続できない場合は socketfilterfw を手動実行"
            "（または sudoers にNOPASSWD設定）してください。"
        )
        return True

    try:
        subprocess.run(sudo_prefix + [_SOCKETFILTERFW, "--remove", resolved], check=False)
    except (FileNotFoundError, OSError) as exc:
        logger.warning("[FIREWALL] firewall remove command failed: %s", exc)

    if not _run_sudo(sudo_prefix + [_SOCKETFILTERFW, "--add", resolved]):
        if interactive:
            logger.error("[FIREWALL] failed to add macOS firewall exception.")
            logger.error("[FIREWALL] macOSファイアウォール許可の追加に失敗しました。")
            return False
        logger.warning(
            "[FIREWALL] failed to add macOS firewall exception; continuing "
            "non-interactive LAN startup."
        )
        logger.warning(
            "[FIREWALL] macOSファイアウォール許可の追加に失敗しましたが、"
            "非対話LAN起動を継続します。"
        )
        return True

    if not _run_sudo(sudo_prefix + [_SOCKETFILTERFW, "--unblockapp", resolved]):
        if interactive:
            logger.error("[FIREWALL] failed to unblock macOS firewall exception.")
            logger.error("[FIREWALL] macOSファイアウォール許可の解除に失敗しました。")
            return False
        logger.warning(
            "[FIREWALL] failed to unblock macOS firewall exception; continuing "
            "non-interactive LAN startup."
        )
        logger.warning(
            "[FIREWALL] macOSファイアウォール許可の解除に失敗しましたが、"
            "非対話LAN起動を継続します。"
        )
        return True

    if cdhash is not None:
        try:
            stamp_path.write_text(cdhash + "\n", encoding="utf-8")
        except OSError as exc:
            logger.warning(
                "[FIREWALL] failed to write firewall cdhash stamp: %s", exc
            )

    return True
