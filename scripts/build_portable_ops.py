"""Build operations for the portable packaging script."""

from __future__ import annotations

import hashlib
import io
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path

# Pinned by SHA-256 because the build extracts this archive and ships it.
#
# Only 3.13.x is listed: `pyproject.toml` declares `requires-python =
# ">=3.13,<3.14"`, so a portable build bundling 3.11 produces an app that cannot
# start. `download_python_embed` raises on anything not listed, so an old
# `--python-version 3.11.9` invocation now fails loudly instead of shipping one.
#
# The digest was measured by fetching the archive from python.org twice and
# confirming both fetches agreed (2026-09-02).
_PYTHON_EMBED_SHA256 = {
    "3.13.15": "d1f04d990aee1253d8569e8e5104e30fa9f5fa830899f14843448872d936a2cf"
}
_GET_PIP_URL = (
    "https://raw.githubusercontent.com/pypa/get-pip/953091ced35f07ab1b09f79ddb864779bd06a78b/public/get-pip.py"
)
_GET_PIP_SHA256 = "25b5c39ade96bab5eabe6404ce83cab6da2deb5fe3c07d9881f43803edb6f9c8"


def download_python_embed(version: str, dest: Path, msg_fn) -> None:
    expected = _PYTHON_EMBED_SHA256.get(version)
    if expected is None:
        raise ValueError(f"unsupported Python embed version: {version}")
    url = f"https://www.python.org/ftp/python/{version}/python-{version}-embed-amd64.zip"
    print(msg_fn("dl_python").format(ver=version))
    print(msg_fn("dl_url").format(url=url))
    req = urllib.request.Request(url, headers={"User-Agent": "YU-AI-Manager-Build/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("Python embed SHA-256 mismatch")
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(dest)
    print(msg_fn("dl_done").format(ver=version, size=f"{len(data) / 1024 / 1024:.1f}"))


def setup_pip(python_exe: Path, msg_fn) -> None:
    print(msg_fn("install_pip"))
    get_pip_path = python_exe.parent / "get-pip.py"
    req = urllib.request.Request(_GET_PIP_URL, headers={"User-Agent": "YU-AI-Manager-Build/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    if hashlib.sha256(data).hexdigest() != _GET_PIP_SHA256:
        raise ValueError("get-pip.py SHA-256 mismatch")
    get_pip_path.write_bytes(data)
    subprocess.run([str(python_exe), str(get_pip_path), "--no-warn-script-location"], check=True)
    get_pip_path.unlink()
    print(msg_fn("install_pip_done"))


def enable_site_packages(python_dir: Path, msg_fn) -> None:
    pth_files = list(python_dir.glob("python*._pth"))
    if not pth_files:
        print(msg_fn("pth_not_found"))
        return
    pth_file = pth_files[0]
    content = pth_file.read_text(encoding="utf-8").replace("#import site", "import site")
    if "Lib\\site-packages" not in content:
        content += "\nLib\\site-packages\n"
    # Add parent dir (..) so that bundle/ (app root) is on sys.path.
    # Python embeddable ignores cwd and script-dir; only _pth entries are used.
    if ".." not in content.split():
        content += "\n..\n"
    pth_file.write_text(content, encoding="utf-8")
    print(msg_fn("pth_edited").format(name=pth_file.name))


def install_deps(python_exe: Path, req_file: Path, msg_fn) -> None:
    print(msg_fn("install_deps"))
    subprocess.run(
        [
            str(python_exe),
            "-m",
            "pip",
            "install",
            "--require-hashes",
            "-r",
            str(req_file),
            "--no-warn-script-location",
        ],
        check=True,
    )
    print(msg_fn("install_deps_done"))


def cleanup_python_dir(python_dir: Path, msg_fn) -> None:
    removed = 0
    for directory in python_dir.rglob("__pycache__"):
        if directory.is_dir():
            shutil.rmtree(directory)
            removed += 1
    for dist_info in python_dir.rglob("*.dist-info"):
        if dist_info.is_dir():
            for child in dist_info.iterdir():
                if (
                    child.name not in ("METADATA", "INSTALLER", "RECORD", "top_level.txt", "entry_points.txt")
                    and child.is_file()
                ):
                    child.unlink()
                    removed += 1
    for name in ("tests", "test"):
        for directory in python_dir.rglob(name):
            if directory.is_dir() and "site-packages" in str(directory):
                shutil.rmtree(directory)
                removed += 1
    print(msg_fn("cleanup_done").format(n=removed))


def copy_app_files(
    src: Path,
    dest: Path,
    exclude_dirs: set[str],
    exclude_files: set[str],
    exclude_top_patterns: set[str],
    msg_fn,
    exclude_file_patterns: set[str] | None = None,
) -> None:
    import fnmatch

    print(msg_fn("copy_start"))
    count = 0
    for item in src.iterdir():
        name = item.name
        # Skip hidden dot-files/dirs (e.g. .playwright-mcp, .tmp_i18n, .dockerignore)
        if name.startswith("."):
            continue
        if name in exclude_top_patterns:
            continue
        if name in exclude_dirs and item.is_dir():
            continue
        if name in exclude_files and item.is_file():
            continue
        if exclude_file_patterns and item.is_file():  # noqa: SIM102
            if any(fnmatch.fnmatch(name, pat) for pat in exclude_file_patterns):
                continue
        if name == "data" and item.is_dir():
            (dest / "data").mkdir(exist_ok=True)
            continue
        if name in {"python", "release"}:
            continue
        if item.is_dir():
            shutil.copytree(
                item,
                dest / name,
                ignore=shutil.ignore_patterns(
                    "__pycache__",
                    "*.pyc",
                    ".mypy_cache",
                    ".pytest_cache",
                    # docs internal subdirs
                    "development",
                    "investigations",
                    "superpowers",
                ),
            )
        else:
            shutil.copy2(item, dest / name)
        count += 1
    print(msg_fn("copy_done").format(n=count))


def build_typescript(root: Path, msg_fn) -> None:
    dist_dir = root / "ui" / "default" / "static" / "dist"
    if dist_dir.exists() and list(dist_dir.glob("*.js")):
        print(msg_fn("ts_skip_existing"))
        return
    build_script = root / "build.mjs"
    if not build_script.exists():
        print(msg_fn("ts_no_build_mjs"))
        return
    if not shutil.which("node"):
        print(msg_fn("ts_no_node"))
        return
    if not (root / "node_modules").exists():
        pkg_mgr = "pnpm" if shutil.which("pnpm") else "npm"
        print(msg_fn("ts_pkg_install").format(mgr=pkg_mgr))
        subprocess.run([pkg_mgr, "install"], cwd=str(root), check=True)
    print(msg_fn("ts_build_start"))
    subprocess.run(["node", "build.mjs"], cwd=str(root), check=True)
    print(msg_fn("ts_build_done"))
