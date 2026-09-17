"""UI installation helpers — git clone, ZIP, 7z extraction."""

import logging
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from .manifest import load_ui_manifest

logger = logging.getLogger(__name__)

_ALLOWED_SCHEMES = {"https", "http"}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _ui_root() -> Path:
    return _project_root() / "ui"


def _validate_url(url: str) -> str | None:
    """Return error string if URL is invalid, else None."""
    try:
        parsed = urlparse(url)
    except Exception:
        return "Invalid URL format"
    if not parsed.scheme or parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        return "Only https:// and http:// URLs are allowed"
    if not parsed.netloc:
        return "URL must include a hostname"
    return None


def _detect_type(url: str) -> str:
    """Detect install type: 'zip', '7z', or 'git'."""
    lower = url.lower().rstrip("/")
    if lower.endswith(".zip"):
        return "zip"
    if lower.endswith(".7z"):
        return "7z"
    return "git"


def _download_file(url: str, dest: Path) -> tuple[dict, int]:
    """Download a file from URL to dest. Returns ({}, 200) or (error, status)."""
    import urllib.request

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "YU-AI-Manager/2.90"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            dest.write_bytes(resp.read())
    except Exception as exc:
        return {"error": f"Download failed: {exc}"}, 500
    return {}, 200


def _install_zip(url: str, target_dir: Path) -> tuple[dict, int]:
    """Download and extract a ZIP archive."""
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        err, status = _download_file(url, tmp_path)
        if status != 200:
            return err, status
        with zipfile.ZipFile(tmp_path) as zf:
            # Check if all files share a common root directory
            names = zf.namelist()
            roots = {n.split("/")[0] for n in names if "/" in n}
            if len(roots) == 1:
                # Single root dir inside zip — extract and move
                extract_base = target_dir.parent
            else:
                target_dir.mkdir(parents=True, exist_ok=True)
                extract_base = target_dir
            # ZIP slip prevention: validate all entry paths
            real_base = os.path.realpath(str(extract_base))
            for info in zf.infolist():
                target = os.path.realpath(
                    os.path.join(real_base, info.filename),
                )
                if (
                    not target.startswith(real_base + os.sep)
                    and target != real_base
                ):
                    raise ValueError(
                        f"ZIP slip detected: {info.filename}"
                    )
            zf.extractall(extract_base)
            if len(roots) == 1:
                extracted = target_dir.parent / roots.pop()
                if extracted != target_dir:
                    extracted.rename(target_dir)
    except zipfile.BadZipFile:
        return {"error": "Downloaded file is not a valid ZIP"}, 400
    except Exception as exc:
        return {"error": f"ZIP extraction failed: {exc}"}, 500
    finally:
        tmp_path.unlink(missing_ok=True)
    return {}, 200


def _install_7z(url: str, target_dir: Path) -> tuple[dict, int]:
    """Download and extract a 7z archive using 7z CLI."""
    from core.sevenz_core.sevenz_cli import extract_to_dir, list_names, sevenz_available

    if not sevenz_available():
        return {"error": "7z CLI not available (install 7-Zip)"}, 500

    with tempfile.NamedTemporaryFile(suffix=".7z", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        err, status = _download_file(url, tmp_path)
        if status != 200:
            return err, status
        names = list_names(str(tmp_path))
        # 7z path traversal prevention: reject dangerous entries
        for name in names:
            if os.path.isabs(name) or ".." in name.split("/"):
                raise ValueError(
                    f"Path traversal detected in 7z: {name}"
                )
        roots = {n.split("/")[0] for n in names if "/" in n}
        if len(roots) == 1:
            extract_to_dir(str(tmp_path), str(target_dir.parent))
            extracted = target_dir.parent / roots.pop()
            if extracted != target_dir:
                extracted.rename(target_dir)
        else:
            target_dir.mkdir(parents=True, exist_ok=True)
            extract_to_dir(str(tmp_path), str(target_dir))
    except Exception as exc:
        err_str = str(exc).lower()
        if "cannot open" in err_str or "not a 7z" in err_str:
            return {"error": "Downloaded file is not a valid 7z archive"}, 400
        return {"error": f"7z extraction failed: {exc}"}, 500
    finally:
        tmp_path.unlink(missing_ok=True)
    return {}, 200


def _install_git(url: str, target_dir: Path) -> tuple[dict, int]:
    """Clone a git repo."""
    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", url, str(target_dir)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        if result.returncode != 0:
            return {"error": "git clone failed", "detail": result.stderr[:500]}, 500
    except FileNotFoundError:
        return {"error": "git is not installed"}, 500
    except subprocess.TimeoutExpired:
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        return {"error": "git clone timed out (120s)"}, 500
    return {}, 200


def install_ui(url: str) -> tuple[dict, int]:
    """Install a UI from a URL (git / ZIP / 7z).

    Returns (response_dict, http_status).
    """
    err = _validate_url(url)
    if err:
        return {"error": err}, 400

    install_type = _detect_type(url)
    ui_root = _ui_root()
    ui_root.mkdir(parents=True, exist_ok=True)

    # Determine target directory name
    if install_type == "git":
        name = url.rstrip("/").split("/")[-1]
        if name.endswith(".git"):
            name = name[:-4]
    else:
        name = Path(urlparse(url).path).stem

    # Sanitize name
    name = "".join(c for c in name if c.isalnum() or c in "-_").strip("-_")
    if not name or name == "default":
        return {"error": "Invalid UI name (reserved or empty)"}, 400

    target_dir = ui_root / name
    if target_dir.exists():
        return {"error": f"UI '{name}' already exists"}, 409

    # Install
    installers = {"git": _install_git, "zip": _install_zip, "7z": _install_7z}
    result, status = installers[install_type](url, target_dir)
    if status != 200:
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        return result, status

    # Validate manifest
    manifest = load_ui_manifest(target_dir)
    if manifest is None:
        shutil.rmtree(target_dir, ignore_errors=True)
        return {"error": "Installed UI has no valid manifest.json"}, 400

    logger.info("Installed UI '%s' from %s (%s)", name, url, install_type)
    return {"name": name, "manifest": manifest}, 200
