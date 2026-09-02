"""Portable ZIP build script (Windows amd64)."""

from __future__ import annotations

import argparse
import platform
import sys
import tempfile
import zipfile
from pathlib import Path

from build_portable_i18n import detect_lang, msg
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

EXCLUDE_DIRS = {
    ".git", ".github", ".claude", "node_modules", "venv", "src-tauri",
    "src", "tests", "cache", "screenshots", "reports", "__pycache__",
    "release", ".mypy_cache", ".pytest_cache",
    "archive", "logs", "backup", "docker", "deploy",
}
EXCLUDE_FILES = {
    ".pip_stamp", ".gitignore", ".gitattributes", ".editorconfig",
    "config.json", "tsconfig.json", "build.mjs", "package.json",
    "pnpm-lock.yaml", ".eslintrc.json", "nul",
    # dev-only files
    "tags.db", "tags.db-wal", "tags.db-shm",
    "vectors.db", "vectors.db-wal", "vectors.db-shm",
    "CLAUDE.md", "CLAUDE_ARCH.md", "CLAUDE_HAILO.md",
    "AGENTS.md", "TODO.md", "CHANGELOG.md", "conftest.py",
    "config_test.json", "launch-args.txt", ".public-exclude",
    "_untranslated_count.txt",
    # logs / dev utilities
    "yu-ai-manager.log",
    "debug_check.py", "db_health.py",
    "fix_gitignore.sh", "organize_docs.sh", "run_tests.sh",
    "pytest.ini",
    "docker-compose.yml", "docker-compose.hailo.yml",
}
# fnmatch patterns for top-level files
EXCLUDE_FILE_PATTERNS = {"_untranslated_*.json"}
EXCLUDE_TOP_PATTERNS = {"=41.0.0"}

LANG = detect_lang()


def tr(key: str) -> str:
    return msg(LANG, key)


def build_archive(output_dir: Path, archive_name: str, work_dir: Path) -> Path:
    """Create the final ZIP archive from the populated work directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / f"{archive_name}.zip"
    print(tr("zip_creating").format(path=zip_path))
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for file_path in work_dir.rglob("*"):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(work_dir.parent))
    print(tr("build_done").format(path=zip_path, size=f"{zip_path.stat().st_size / 1024 / 1024:.1f}"))
    return zip_path


def build_portable(args) -> None:
    version_file = ROOT / "VERSION"
    app_version = version_file.read_text().strip() if version_file.exists() else "0.0.0"
    archive_name = f"YU-AI-Manager-v{app_version}-Portable-win-amd64"

    print(tr("build_start").format(ver=app_version))
    print(tr("build_python_label").format(ver=args.python_version))
    print(tr("build_output_label").format(path=f"{args.output_dir}/{archive_name}.zip"))
    print()

    if not args.skip_ts_build:
        build_typescript(ROOT, tr)

    dist_dir = ROOT / "ui" / "default" / "static" / "dist"
    if not dist_dir.exists() or not list(dist_dir.glob("*.js")):
        print(tr("err_no_dist_js"))
        print(tr("err_run_build_first"))
        sys.exit(1)

    with tempfile.TemporaryDirectory(prefix="yu-portable-") as tmpdir:
        work_dir = Path(tmpdir) / archive_name
        work_dir.mkdir()

        python_dir = work_dir / "python"
        download_python_embed(args.python_version, python_dir, tr)
        enable_site_packages(python_dir, tr)

        python_exe = python_dir / "python.exe"
        setup_pip(python_exe, tr)

        req_file = ROOT / "requirements-portable.lock"
        install_deps(python_exe, req_file, tr)
        cleanup_python_dir(python_dir, tr)

        copy_app_files(ROOT, work_dir, EXCLUDE_DIRS, EXCLUDE_FILES, EXCLUDE_TOP_PATTERNS, tr, EXCLUDE_FILE_PATTERNS)
        (work_dir / "data").mkdir(exist_ok=True)
        build_archive(Path(args.output_dir), archive_name, work_dir)


def parse_args():
    parser = argparse.ArgumentParser(description=tr("arg_desc"))
    parser.add_argument("--python-version", default="3.13.15", help=tr("arg_pyver"))
    parser.add_argument("--output-dir", default=str(ROOT / "release"), help=tr("arg_outdir"))
    parser.add_argument("--skip-ts-build", action="store_true", help=tr("arg_skip_ts"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if platform.system() != "Windows":
        print(tr("err_windows_only"))
        sys.exit(1)
    build_portable(args)


if __name__ == "__main__":
    main()
