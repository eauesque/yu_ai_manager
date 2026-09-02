"""Flask Web UI entrypoint and compatibility exports.

Automatically creates/activates a venv and re-executes when launched outside one.
Prefers uv-managed `.venv` and falls back to legacy `venv/` for compatibility.
"""

import os
import sys


def _venv_python(base, name: str, is_windows: bool):
    """Return the python executable path inside a venv directory."""
    venv_dir = base / name
    return (
        venv_dir / "Scripts" / "python.exe"
        if is_windows
        else venv_dir / "bin" / "python"
    )


def _reexec(python_exe, is_windows: bool) -> None:
    """Re-launch the current script under a different python interpreter."""
    import subprocess

    print(f"[BOOTSTRAP] Re-launching with {python_exe}...")
    if is_windows:
        # Windows: os.execv is unreliable, use subprocess + sys.exit instead
        result = subprocess.run([str(python_exe), *sys.argv])
        sys.exit(result.returncode)
    else:
        os.execv(str(python_exe), [str(python_exe), *sys.argv])


def _bootstrap() -> None:
    """Resolve a Python environment with deps installed, then re-launch under it.

    Priority: bundled portable python > current venv > .venv (uv) > venv
    (legacy) > create with uv > create with stdlib venv + pip. Returns when
    already inside a usable interpreter; otherwise replaces the process via
    os.execv (POSIX) or subprocess + sys.exit (Windows).
    """
    import platform
    import shutil
    import subprocess
    from pathlib import Path

    base = Path(__file__).resolve().parent
    is_windows = platform.system() == "Windows"

    # Portable mode: no venv needed if launched from ./python/python.exe
    portable_python = base / "python" / ("python.exe" if is_windows else "python")
    if portable_python.exists():
        exe_parent = Path(sys.executable).resolve().parent
        if exe_parent == portable_python.resolve().parent:
            return

    # Already inside any venv -- nothing to do
    if sys.prefix != sys.base_prefix:
        return

    # Detect existing venvs in priority order: uv-managed `.venv` first, then legacy `venv`
    uv_venv_python = _venv_python(base, ".venv", is_windows)
    legacy_venv_python = _venv_python(base, "venv", is_windows)

    has_uv = shutil.which("uv") is not None
    has_pyproject = (base / "pyproject.toml").exists()

    # Re-launch into existing venv if available
    if uv_venv_python.exists():
        _maybe_sync_dependencies(base, uv_venv_python, has_uv, has_pyproject)
        _reexec(uv_venv_python, is_windows)
    if legacy_venv_python.exists():
        _maybe_sync_dependencies(base, legacy_venv_python, has_uv, has_pyproject)
        _reexec(legacy_venv_python, is_windows)

    # No venv exists -- create one. Prefer uv when available + pyproject present.
    if has_uv and has_pyproject:
        print("[BOOTSTRAP] No venv found -- running 'uv sync'...")
        try:
            subprocess.run(["uv", "sync"], cwd=str(base), check=True)
        except subprocess.CalledProcessError as e:
            print(f"[BOOTSTRAP] 'uv sync' failed: {e}", file=sys.stderr)
            sys.exit(1)
        if uv_venv_python.exists():
            _reexec(uv_venv_python, is_windows)

    # Fallback: stdlib venv + pip/uv pip install
    print("[BOOTSTRAP] Creating legacy venv/...")
    try:
        subprocess.run(
            [sys.executable, "-m", "venv", "venv"],
            cwd=str(base),
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"[BOOTSTRAP] Failed to create venv: {e}", file=sys.stderr)
        sys.exit(1)
    _maybe_sync_dependencies(base, legacy_venv_python, has_uv, has_pyproject)
    _reexec(legacy_venv_python, is_windows)


def _maybe_sync_dependencies(base, venv_python, has_uv: bool, has_pyproject: bool) -> None:
    """Install/sync dependencies if the manifest is newer than our stamp file."""
    import subprocess

    req_file = base / "requirements.txt"
    pyproject = base / "pyproject.toml"
    uv_lock = base / "uv.lock"

    # Pick the manifest that drives "needs install" detection.
    if has_uv and has_pyproject:
        manifest = uv_lock if uv_lock.exists() else pyproject
        stamp_file = base / ".uv_stamp"
    elif req_file.exists():
        manifest = req_file
        stamp_file = base / ".pip_stamp"
    else:
        return

    needs_install = not stamp_file.exists() or (
        manifest.stat().st_mtime > stamp_file.stat().st_mtime
    )
    if not needs_install:
        return

    print(f"[BOOTSTRAP] Installing Python dependencies (manifest: {manifest.name})...")
    if has_uv and has_pyproject:
        # `uv sync` only manages the .venv at base/.venv. If the user's
        # existing venv is the legacy one, fall back to `uv pip install`.
        if venv_python.parent.parent.name == ".venv":
            cmd = ["uv", "sync"]
        elif req_file.exists():
            cmd = ["uv", "pip", "install", "--python", str(venv_python),
                   "-r", "requirements.txt"]
        else:
            cmd = ["uv", "pip", "install", "--python", str(venv_python),
                   "-e", "."]
    else:
        cmd = [str(venv_python), "-m", "pip", "install", "-r", "requirements.txt"]

    try:
        subprocess.run(cmd, cwd=str(base), check=True)
        stamp_file.touch()
        print("[BOOTSTRAP] Dependencies installed successfully")
    except subprocess.CalledProcessError as e:
        print(f"[BOOTSTRAP] Dependency install failed: {e}", file=sys.stderr)
        # Continue -- some packages may already be installed


def _seed_example_files(base=None) -> None:
    """Copy .example template files to their real names on first launch.

    Without this, fresh clones / unpacked archives have no launch-args.txt
    or config.json, leaving users with an empty default-config experience
    and no obvious starting point for tweaks.
    """
    import os
    import shutil
    from pathlib import Path

    base = Path(__file__).resolve().parent if base is None else Path(base)
    launch_args = base / "launch-args.txt"
    launch_args_backup = base / "launch-args.txt.pytest_bak"
    if not launch_args.exists() and launch_args_backup.exists():
        os.replace(launch_args_backup, launch_args)
        print("[BOOTSTRAP] Recovered launch-args.txt from launch-args.txt.pytest_bak")

    pairs = (
        ("launch-args.txt.example", "launch-args.txt"),
        ("config.json.example", "config.json"),
    )
    for src_name, dst_name in pairs:
        src = base / src_name
        dst = base / dst_name
        if dst.exists() or not src.exists():
            continue
        try:
            shutil.copy2(src, dst)
            print(f"[BOOTSTRAP] Seeded {dst_name} from {src_name}")
        except OSError as exc:
            print(f"[BOOTSTRAP] Failed to seed {dst_name}: {exc}", file=sys.stderr)


# -- Entry point --

if __name__ == "__main__":
    from scripts.post_restart_apply import apply_pending_replacements
    apply_pending_replacements()
    _bootstrap()
    # _bootstrap() returned = already inside a usable interpreter

    # Detect a stale TS bundle (src/ts/ was edited or pulled but pnpm build
    # was never run). Exit 75 (EX_TEMPFAIL) so start.sh / start.bat can
    # intercept and run the build automatically. Set YU_SKIP_DIST_CHECK=1
    # to bypass.
    try:
        from scripts.check_dist_freshness import check as _dist_check
        _fresh, _reason = _dist_check()
        if not _fresh:
            # Attempt an inline rebuild before delegating to the start script.
            # Covers direct invocations (IDE, Tauri sidecar, uv run ...) where
            # exit code 75 is never caught by a start.sh/start.bat wrapper.
            try:
                import shutil as _shutil
                import subprocess as _subprocess
                from pathlib import Path as _Path
                _base = _Path(__file__).parent
                if _shutil.which("node") and (_base / "build.mjs").exists():
                    if not (_base / "node_modules" / "dictionary-en").exists() and _shutil.which("pnpm"):
                        print("[INFO] node_modules incomplete — running pnpm install...", file=sys.stderr)
                        import os as _os
                        _subprocess.run(
                            ["pnpm", "install"],
                            cwd=str(_base),
                            timeout=120,
                            env={**_os.environ, "CI": "1"},
                        )
                    print(
                        f"[INFO] dist out of date ({_reason}) — running inline build...",
                        file=sys.stderr,
                    )
                    _br = _subprocess.run(
                        ["node", "build.mjs"],
                        cwd=str(_base),
                        timeout=120,
                    )
                    if _br.returncode == 0:
                        _fresh, _reason = _dist_check()
                        print("[INFO] Inline build succeeded.", file=sys.stderr)
                        # The launcher already asked fast_mode.py whether the
                        # Rust server may be used, and got "no: the bundle is
                        # stale". That answer is now wrong, and because this
                        # path boots normally (no exit 75) the launcher's
                        # dist-retry branch -- which re-asks -- never runs. Ask
                        # again here, or this launch acquires nothing and the
                        # settings screen keeps reporting the staleness that
                        # was just fixed.
                        try:
                            from scripts.fast_mode import refresh_after_dist_rebuild
                            refresh_after_dist_rebuild(_base)
                        except Exception as _refresh_exc:  # noqa: BLE001
                            print(
                                f"[INFO] fast-mode re-check skipped: {_refresh_exc}",
                                file=sys.stderr,
                            )
                    else:
                        print(
                            f"[WARNING] Inline build failed (exit {_br.returncode}).",
                            file=sys.stderr,
                        )
            except Exception as _build_exc:
                print(f"[INFO] Inline build skipped: {_build_exc}", file=sys.stderr)

            if not _fresh:
                print(
                    f"\n[WARNING] Web UI bundle is out of date: {_reason}\n"
                    "          Run `pnpm run build` (start.sh / start.bat will "
                    "do it automatically).\n",
                    file=sys.stderr,
                )
                sys.exit(75)
    except Exception as _exc:  # noqa: BLE001 — never block startup on the check
        print(f"[INFO] dist freshness check skipped: {_exc}", file=sys.stderr)

    _seed_example_files()
    # Initialize writable paths (data/, cache/, logs/, profiles/) before
    # any core.* module that depends on them is imported. Env vars
    # (TAGDB_DATA_DIR etc.) from the Tauri installer take priority.
    from core.paths import init_app_paths
    init_app_paths()
    from core.system.safe_mode import SafeModeManager
    SafeModeManager().sync_startup_marker()
    from core.web.runtime import run_web_ui
    sys.exit(run_web_ui())

# Exports for import usage (when other modules import web_ui)
try:
    from core.web.runtime import create_app, run_web_ui  # noqa: F811

    __all__ = ["create_app", "main"]

    def main() -> int:
        return run_web_ui()
except ImportError:
    # Flask is not available when imported from outside venv
    pass
