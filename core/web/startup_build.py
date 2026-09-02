"""Auto-rebuild TypeScript / auto-install Python deps at startup."""

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_PREFIX = "[BUILD]"
_PIP_PREFIX = "[DEPS]"
_STAMP = ".pip_stamp"


def maybe_install_deps() -> None:
    """Run ``uv pip install -r requirements.txt`` if requirements.txt is newer than stamp."""

    base = Path(__file__).resolve().parents[2]  # project root

    # Portable mode: dependencies are pre-installed
    if (base / "python" / "python.exe").exists() or (base / "python" / "python").exists():
        return

    req_file = base / "requirements.txt"
    stamp_file = base / _STAMP

    if not req_file.exists():
        return

    # Compare mtime: stamp records when we last ran install
    if stamp_file.exists() and req_file.stat().st_mtime <= stamp_file.stat().st_mtime:
        return  # already up-to-date

    # Prefer uv pip, fall back to pip
    if shutil.which("uv"):
        cmd = ["uv", "pip", "install", "-r", "requirements.txt"]
    elif shutil.which("pip"):
        cmd = ["pip", "install", "-r", "requirements.txt"]
    else:
        logger.info(f"  {_PIP_PREFIX} uv/pip not found -skipping dependency install")
        return

    logger.info(f"  {_PIP_PREFIX} requirements.txt updated -installing dependencies...")
    try:
        result = subprocess.run(
            cmd,
            cwd=str(base),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        if result.returncode == 0:
            logger.info(f"  {_PIP_PREFIX} Install succeeded")
            # Touch stamp file
            stamp_file.touch()
        else:
            logger.info(f"  {_PIP_PREFIX} Install failed (exit {result.returncode})")
            if result.stderr:
                for line in result.stderr.strip().splitlines()[:10]:
                    logger.info(f"  {_PIP_PREFIX}   {line}")
    except Exception as exc:
        logger.info(f"  {_PIP_PREFIX} Install error: {exc}")


def maybe_rebuild_ts() -> None:
    """Run ``node build.mjs`` if dist/ is stale or missing.

    Uses ``scripts/check_dist_freshness.py`` (sha256 of all ``src/ts/**/*.ts``
    matched against ``dist/.build-info.json``) instead of mtime comparison.
    Mtime is unreliable across ``git pull`` / ``git checkout`` because:
      - removed dist files leave stale companions whose mtime predates the pull
      - unchanged TS files keep their old mtime, so the comparison can falsely
        conclude "dist is newer" even when expected entry bundles are missing.
    """

    base = Path(__file__).resolve().parents[2]  # project root
    src_dir = base / "src" / "ts"
    build_script = base / "build.mjs"

    if not src_dir.exists():
        return  # distributed package without TS sources

    if not build_script.exists():
        return

    if not shutil.which("node"):
        logger.info(f"  {_PREFIX} node not found -skipping TypeScript build check")
        return

    # Defer to the canonical freshness check used by start.sh / start.bat /
    # web_ui.py so we can't drift from their decision.
    try:
        import sys
        scripts_dir = base / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        import check_dist_freshness  # type: ignore[import-not-found]
        fresh, reason = check_dist_freshness.check()
    except Exception as exc:  # pragma: no cover - fall back to forcing build
        logger.info(f"  {_PREFIX} freshness check failed ({exc}) - forcing rebuild")
        fresh, reason = False, "freshness check error"

    if fresh:
        return

    logger.info(f"  {_PREFIX} dist out of date ({reason}) - rebuilding...")

    # Ensure node_modules exist (esbuild is a devDependency)
    node_modules = base / "node_modules"
    if not node_modules.exists():
        if shutil.which("pnpm"):
            install_cmd = ["pnpm", "install"]
        elif shutil.which("npm"):
            install_cmd = ["npm", "install"]
        else:
            logger.info(f"  {_PREFIX} pnpm/npm not found -- cannot install Node dependencies")
            return
        logger.info(f"  {_PREFIX} node_modules missing -- running {install_cmd[0]} install...")
        try:
            inst = subprocess.run(
                install_cmd, cwd=str(base),
                capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=120,
            )
            if inst.returncode != 0:
                logger.info(f"  {_PREFIX} {install_cmd[0]} install failed (exit {inst.returncode})")
                if inst.stderr:
                    for line in inst.stderr.strip().splitlines()[:10]:
                        logger.info(f"  {_PREFIX}   {line}")
                return
            logger.info(f"  {_PREFIX} {install_cmd[0]} install succeeded")
        except Exception as exc:
            logger.info(f"  {_PREFIX} Install error: {exc}")
            return

    try:
        result = subprocess.run(
            ["node", "build.mjs"],
            cwd=str(base),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        if result.returncode == 0:
            logger.info(f"  {_PREFIX} Build succeeded")
        else:
            logger.info(f"  {_PREFIX} Build failed (exit {result.returncode})")
            if result.stderr:
                for line in result.stderr.strip().splitlines()[:10]:
                    logger.info(f"  {_PREFIX}   {line}")
    except Exception as exc:
        logger.info(f"  {_PREFIX} Build error: {exc}")
