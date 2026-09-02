"""Markdown file scanner.

Walks scan_roots to collect .md/.markdown files and upserts them
into the DB. Unchanged files are skipped via mtime comparison.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from core.services_core.db_state import get_readonly_db

from .store import ensure_tables, get_md_file_by_path, mark_missing_deleted, upsert_md_file

try:
    from langdetect import detect as _langdetect
    _HAS_LANGDETECT = True
except ImportError:
    _HAS_LANGDETECT = False

if TYPE_CHECKING:
    from core.jobs_core.jobs_model import Job

logger = logging.getLogger(__name__)

# Excluded directory names
_EXCLUDED_DIRS = frozenset({
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", ".eggs",
    "dist", "build", ".next", ".nuxt",
})

# Target extensions
_MD_EXTENSIONS = frozenset({".md", ".markdown"})

# File size limit (5 MB)
_MAX_FILE_SIZE = 5 * 1024 * 1024


def scan_md_files(
    scan_roots: list[str],
    job: Job | None = None,
) -> dict:
    """Scan MD files under scan_roots and register them in the DB.

    Returns:
        Statistics dict (found, new, updated, skipped, deleted, errors)
    """
    read_con = get_readonly_db()
    ensure_tables()

    if job:
        job.update(phase="collecting", message="Collecting MD files...")

    # Phase 1: file collection
    md_paths = _collect_md_files(scan_roots)
    total = len(md_paths)

    if job:
        job.progress(0, total, "")
        job.update(phase="indexing", message=f"Processing {total} MD files...")

    stats = {"found": total, "new": 0, "updated": 0, "skipped": 0, "errors": 0}
    found_paths: set[str] = set()

    # Phase 2: upsert
    for i, fpath in enumerate(md_paths):
        if job and job.cancelled:
            job.complete_cancelled()
            return stats

        path_str = str(fpath)
        found_paths.add(path_str)

        try:
            st = fpath.stat()
            file_mtime = st.st_mtime
            file_size = st.st_size

            # Check size limit
            if file_size > _MAX_FILE_SIZE:
                stats["skipped"] += 1
                continue

            # Determine skip by mtime comparison
            # Re-process if: lang missing, or path-based lang differs from stored
            existing = get_md_file_by_path(read_con, path_str)
            if existing and abs(existing["mtime"] - file_mtime) < 0.01:
                stored_lang = existing.get("lang", "")
                path_lang = _detect_language_from_path(path_str)
                # Skip only if lang is populated AND consistent with path
                if stored_lang and (not path_lang or stored_lang == path_lang):
                    stats["skipped"] += 1
                    if job:
                        job.progress(i + 1, total, fpath.name)
                    continue

            # Read file
            content = _read_file(fpath)
            title = _extract_title(content, fpath.stem)
            lang = _detect_language(content, file_path=path_str)

            upsert_md_file(None, path_str, file_mtime, file_size, title, content, lang=lang)

            if existing:
                stats["updated"] += 1
            else:
                stats["new"] += 1

        except Exception as exc:
            logger.warning("MD scan error: %s: %s", fpath, exc)
            stats["errors"] += 1

        if job:
            job.progress(i + 1, total, fpath.name)

    # Phase 3: soft-delete files not found
    deleted = mark_missing_deleted(None, found_paths)
    stats["deleted"] = deleted

    if job:
        msg = (
            f"Done: {stats['new']} added, {stats['updated']} updated, "
            f"{stats['skipped']} skipped"
        )
        if deleted:
            msg += f", {deleted} deleted"
        job.complete(msg)

    return stats


def _collect_md_files(scan_roots: list[str]) -> list[Path]:
    """Collect MD file paths under scan_roots."""
    result: list[Path] = []
    seen: set[str] = set()

    for root in scan_roots:
        root_path = Path(root)
        if not root_path.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root_path):
            # Skip excluded directories
            dirnames[:] = [
                d for d in dirnames
                if d not in _EXCLUDED_DIRS and not d.startswith(".")
            ]
            for fname in filenames:
                ext = Path(fname).suffix.lower()
                if ext not in _MD_EXTENSIONS:
                    continue
                full = Path(dirpath) / fname
                resolved = str(full.resolve())
                if resolved not in seen:
                    seen.add(resolved)
                    result.append(full)

    return sorted(result)


def _read_file(path: Path) -> str:
    """Read file as UTF-8. Decode errors are replaced."""
    return path.read_text(encoding="utf-8", errors="replace")


def _extract_title(content: str, fallback: str) -> str:
    """Extract the first # heading as title. Use filename if not found."""
    for line in content.split("\n", 20):
        stripped = line.strip()
        if stripped.startswith("# ") and len(stripped) > 2:
            return stripped[2:].strip()
        # Skip empty lines and frontmatter
        if stripped and not stripped.startswith("---"):
            break
    return fallback


# Minimum text length for reliable language detection
_MIN_DETECT_LEN = 40

# Path-based language detection: directory name -> lang code
_PATH_LANG_MAP: dict = {
    "/ja/": "ja", "/en/": "en", "/ko/": "ko",
    "/zh-cn/": "zh-cn", "/zh-tw/": "zh-tw",
    "/de/": "de", "/fr/": "fr", "/es/": "es",
    "/ru/": "ru", "/pt/": "pt", "/it/": "it",
}


def _detect_language_from_path(file_path: str) -> str:
    """Detect language from directory structure (e.g. docs/ja/...).

    Most reliable for projects that organize docs by language directory.
    Returns lang code or '' if no match.
    """
    # Normalize separators
    normalized = file_path.replace("\\", "/")
    for pattern, lang in _PATH_LANG_MAP.items():
        if pattern in normalized:
            return lang
    return ""


def _detect_language(content: str, file_path: str = "") -> str:
    """Detect the primary language of markdown content.

    Strategy: path-based detection first (100% accurate for structured
    docs), then langdetect fallback for files outside language dirs.
    Returns ISO 639-1 code or ''.
    """
    # Priority 1: path-based (deterministic, no false positives)
    if file_path:
        path_lang = _detect_language_from_path(file_path)
        if path_lang:
            return path_lang

    # Priority 2: langdetect (statistical, for unstructured locations)
    if not _HAS_LANGDETECT:
        return ""
    text = _strip_markdown(content)
    if len(text) < _MIN_DETECT_LEN:
        return ""
    try:
        lang = _langdetect(text)
        # Normalize Chinese variants
        if lang == "zh-cn":
            return "zh-cn"
        if lang == "zh-tw":
            return "zh-tw"
        return lang
    except Exception:
        return ""


def _strip_markdown(text: str) -> str:
    """Remove markdown syntax to get plain text for language detection."""
    import re
    # Remove frontmatter
    text = re.sub(r"^---[\s\S]*?---\n?", "", text, count=1)
    # Remove code blocks
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]+`", "", text)
    # Remove headings markers
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove links but keep text: [text](url) -> text
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    # Remove images
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", "", text)
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Remove emphasis markers
    text = re.sub(r"[*_]{1,3}", "", text)
    # Remove table pipes
    text = re.sub(r"\|", " ", text)
    # Remove horizontal rules
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    return text.strip()
