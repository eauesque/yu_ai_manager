"""Stage files for Tauri self-contained NSIS installer.

Usage:
    python scripts/prepare-tauri-bundle.py
    python scripts/prepare-tauri-bundle.py --python-version 3.13.15

Creates src-tauri/bundle/ with:
  - python/          Python Embeddable + site-packages (deps installed)
  - core/, routes/, extensions/, ui/, ...  Application source files
  - web_ui.py        Entry point
  - data/            Empty data directory
"""

import argparse
import platform
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_portable_i18n import detect_lang
from build_portable_i18n import msg as _msg
from build_portable_ops import (
    build_typescript,
    cleanup_python_dir,
    copy_app_files,
    download_python_embed,
    enable_site_packages,
    install_deps,
    setup_pip,
)

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_DIR = ROOT / "src-tauri" / "bundle"

LANG = detect_lang()

EXCLUDE_DIRS = {
    ".git", ".github", ".claude", "node_modules", "venv", "src-tauri",
    "src", "tests", "cache", "screenshots", "reports", "__pycache__",
    "release", ".mypy_cache", ".pytest_cache", ".worktrees",
    # Runtime-generated directories that must not be bundled
    "backup", "logs", "data", "profiles",
    # Dev/infrastructure directories not needed at runtime
    "docs", "tools", "deploy", "docker", "archive", "cli", "static",
    # Other project directories / scaffolds in ROOT
    "tauri-app",
}
EXCLUDE_FILES = {
    ".pip_stamp", ".gitignore", ".gitattributes", ".editorconfig",
    "config.json", "tsconfig.json", "build.mjs", "package.json",
    "pnpm-lock.yaml", ".eslintrc.json", "nul",
    # Runtime-generated database and log files
    "tags.db", "tags.db-shm", "tags.db-wal", "tags.db-journal",
    "yu-ai-manager.log",
    # Dev/test files
    "config_test.json", "conftest.py", "pytest.ini",
    "run_tests.sh", "fix_gitignore.sh", "organize_docs.sh",
    "Dockerfile", "docker-compose.yml", "docker-compose.hailo.yml",
    "launch-args.txt", "launch-args.txt.example",
}
EXCLUDE_TOP_PATTERNS: set[str] = set()


def msg_fn(key: str) -> str:
    return _msg(LANG, key)


def _precompile_bundle(bundle_dir: Path) -> None:
    """Pre-compile Python bytecode so first-run startup is fast.

    cleanup_python_dir() removes __pycache__; this adds them back before zipping.
    The resulting .pyc files are extracted with the bundle and used immediately.
    """
    import subprocess
    python_exe = bundle_dir / "python" / "python.exe"
    if not python_exe.exists():
        print("[BUILD] python.exe not found, skipping pre-compilation.")
        return
    print("[BUILD] Pre-compiling Python bytecode (this may take a minute)...")
    # site-packages: installed libraries (most expensive to import cold)
    site_packages = bundle_dir / "python" / "Lib" / "site-packages"
    if site_packages.exists():
        subprocess.run(
            [str(python_exe), "-m", "compileall", "-q", "-j", "0", str(site_packages)],
            check=False,
        )
    # App source files
    for sub in ["core", "routes", "extensions", "mcp_server"]:
        d = bundle_dir / sub
        if d.exists():
            subprocess.run(
                [str(python_exe), "-m", "compileall", "-q", str(d)],
                check=False,
            )
    print("[BUILD] Pre-compilation done.")


def _copy_help_docs(root: Path, bundle_dir: Path) -> None:
    """Copy help-related docs into bundle/docs/ for the in-app help system.

    Only ja/en languages are bundled (SUPPORTED_LANGS in help_data.py).
    Includes: help/{user,developer}/ and PATH_MAP-referenced files.
    """
    # Subdirs within docs/{lang}/ needed by PATH_MAP in routes/help_data.py
    path_map_subdirs = {"api", "plugin-development", "custom-ui"}
    langs = ("ja", "en")
    copied = 0
    for lang in langs:
        src_lang = root / "docs" / lang
        dst_lang = bundle_dir / "docs" / lang
        # help/user/ and help/developer/
        for cat in ("user", "developer"):
            src_cat = src_lang / "help" / cat
            if not src_cat.exists():
                continue
            dst_cat = dst_lang / "help" / cat
            dst_cat.mkdir(parents=True, exist_ok=True)
            for md in src_cat.glob("*.md"):
                shutil.copy2(md, dst_cat / md.name)
                copied += 1
        # PATH_MAP-referenced subdirs
        for subdir in path_map_subdirs:
            src_sub = src_lang / subdir
            if not src_sub.exists():
                continue
            dst_sub = dst_lang / subdir
            dst_sub.mkdir(parents=True, exist_ok=True)
            for md in src_sub.rglob("*.md"):
                rel = md.relative_to(src_sub)
                dest = dst_sub / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(md, dest)
                copied += 1
    print(f"[BUILD] Help docs copied: {copied} files")


def _create_bundle_zip(bundle_dir: Path, zip_path: Path) -> None:
    """Create bundle.zip (STORE mode) from the staged bundle directory.

    Archive paths start with 'bundle/' so that extracting to exe_dir gives
    exe_dir/bundle/python/python.exe etc.
    NSIS LZMA compresses the zip, so STORE mode avoids double-compression.
    """
    print("[BUILD] Creating bundle.zip (uncompressed - NSIS will compress)...")
    bundle_parent = bundle_dir.parent  # src-tauri/
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
        for f in sorted(bundle_dir.rglob("*")):
            if not f.is_file():
                continue
            # archive path: bundle/relative/path/to/file
            arc_name = f.relative_to(bundle_parent).as_posix()
            zf.write(f, arc_name)
    size_mb = zip_path.stat().st_size / 1024 / 1024
    print(f"[BUILD] bundle.zip: {size_mb:.1f} MB")


# src-tauri/build.rs writes this exact byte string to src-tauri/yu-server.exe
# (a different file from `built` below) so that Tauri's resource validation
# passes on a plain `cargo build`/`cargo test`, before this script has ever
# run. The check below only fires if this same placeholder ever ends up at
# `built`'s path too (crates/target/release/...) -- it does not read or
# detect the placeholder that build.rs writes to src-tauri/yu-server.exe.
# Keeping the two byte strings identical across build.rs, this file, and
# yu_server.rs's test is enforced by tests/test_prepare_tauri_bundle.py, not
# by this comment.
PLACEHOLDER_MARKER = b"YU_AI_MANAGER_PLACEHOLDER_NOT_A_REAL_BINARY\n"


def stage_yu_server(project_root: Path, dest_dir: Path) -> None:
    """Ship the Rust server next to the executable.

    `find_yu_server_bin()` looks in the executable's own directory, so this
    location is the contract -- not `bin/`, which is the git-clone path.
    """
    name = "yu-server.exe" if sys.platform == "win32" else "yu-server"
    built = project_root / "crates" / "target" / "release" / name
    if not built.is_file():
        raise SystemExit(
            f"yu-server が見つかりません: {built}\n"
            "先に `cargo build --release -p yu-server` を実行してください。"
        )
    with built.open("rb") as f:
        head = f.read(len(PLACEHOLDER_MARKER))
    if head == PLACEHOLDER_MARKER:
        raise SystemExit(
            f"[FATAL] {built} は build.rs のプレースホルダのままです。実体の\n"
            "yu-server バイナリではありません。`cargo build --release -p\n"
            "yu-server` が実際に成功したか確認してください。このまま続けると\n"
            "インストーラにプレースホルダが同梱されます。"
        )
    shutil.copy2(built, dest_dir / name)
    print(f"[bundle] staged {name} ({built.stat().st_size // (1024 * 1024)}MB)")


def _stage_python_runtime(python_dir: Path, python_version: str) -> None:
    """Build the embedded runtime from pinned sources; never reuse staged files."""
    shutil.rmtree(python_dir, ignore_errors=True)
    download_python_embed(python_version, python_dir, msg_fn)
    enable_site_packages(python_dir, msg_fn)
    python_exe = python_dir / "python.exe"
    setup_pip(python_exe, msg_fn)
    install_deps(python_exe, ROOT / "requirements-portable.lock", msg_fn)
    cleanup_python_dir(python_dir, msg_fn)


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage files for Tauri NSIS installer")
    parser.add_argument("--python-version", default="3.13.15",
                        help="Python version to bundle (default: 3.13.15)")
    parser.add_argument("--skip-ts-build", action="store_true",
                        help="Skip TypeScript build")
    parser.add_argument("--clean", action="store_true",
                        help="Accepted for compatibility; staging is always rebuilt")
    args = parser.parse_args()

    if platform.system() != "Windows":
        print("[ERROR] Tauri bundle preparation only runs on Windows")
        sys.exit(1)

    version_file = ROOT / "VERSION"
    app_version = version_file.read_text().strip() if version_file.exists() else "0.0.0"

    print(f"[BUILD] Preparing Tauri bundle for YU AI Manager v{app_version}")
    print(f"  Python: {args.python_version}")
    print(f"  Output: {BUNDLE_DIR}")
    print()

    # Rebuild from pinned inputs on every invocation; old files are untrusted.
    if BUNDLE_DIR.exists():
        print("[BUILD] Rebuilding existing bundle/...")
        shutil.rmtree(BUNDLE_DIR)

    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)

    # 1. TypeScript build
    if not args.skip_ts_build:
        build_typescript(ROOT, msg_fn)

    # Verify dist/
    dist_dir = ROOT / "ui" / "default" / "static" / "dist"
    if not dist_dir.exists() or not list(dist_dir.glob("*.js")):
        print(msg_fn("err_no_dist_js"))
        print(msg_fn("err_run_build_first"))
        sys.exit(1)

    # 1b. Fast-mode server binary (D7: bundled next to the exe, not extracted
    #     from bundle.zip -- find_yu_server_bin() only looks in exe_dir).
    stage_yu_server(ROOT, ROOT / "src-tauri")

    # 2. Python Embeddable Package
    python_dir = BUNDLE_DIR / "python"
    _stage_python_runtime(python_dir, args.python_version)

    # 5. Copy application files
    copy_app_files(ROOT, BUNDLE_DIR, EXCLUDE_DIRS, EXCLUDE_FILES, EXCLUDE_TOP_PATTERNS, msg_fn)

    # 5b. Copy help docs (docs/ is excluded from main copy to keep bundle small)
    _copy_help_docs(ROOT, BUNDLE_DIR)

    # 6. Ensure data/ directory
    (BUNDLE_DIR / "data").mkdir(exist_ok=True)

    # 7. Pre-compile Python bytecode for faster first-run startup
    _precompile_bundle(BUNDLE_DIR)

    # 8. Create bundle.zip for NSIS resource bundling (directory structure preserved)
    #    Tauri's bundle/**/* glob flattens files, so we ship a zip and extract on first run.
    _create_bundle_zip(BUNDLE_DIR, ROOT / "src-tauri" / "bundle.zip")

    # Calculate total size
    total = sum(f.stat().st_size for f in BUNDLE_DIR.rglob("*") if f.is_file())
    print(f"\n[BUILD] Bundle staged: {BUNDLE_DIR}")
    print(f"[BUILD] Total size: {total / 1024 / 1024:.1f} MB")
    print("[BUILD] Run 'cargo tauri build' to create the installer.")


if __name__ == "__main__":
    main()
