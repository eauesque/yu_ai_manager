"""Configuration for license audit checks."""

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {
    ".venv",
    "venv",
    "node_modules",
    ".git",
    ".worktrees",
    "data",
    "__pycache__",
    "dist",
    "target",
    "bundle",
    "screenshots",
    "reports",
    ".claude",
}
SOURCE_EXTS = {".py", ".ts", ".js", ".html", ".css", ".json", ".cfg", ".toml", ".txt", ".md", ".rst", ".yaml", ".yml"}
LICENSE_HEADER_PATTERNS = [
    re.compile(r"under the terms of the GNU", re.IGNORECASE),
    re.compile(r"Licensed under.*(GPL|LGPL|AGPL)", re.IGNORECASE),
    re.compile(r"License:\s*(GPL|LGPL|AGPL)", re.IGNORECASE),
    re.compile(r"SPDX-License-Identifier:.*(GPL|LGPL|AGPL)", re.IGNORECASE),
]
FALSE_POSITIVE_PATTERNS = [
    re.compile(r"replaces.*GPL", re.IGNORECASE),
    re.compile(r"instead of.*GPL", re.IGNORECASE),
    re.compile(r"removed.*GPL", re.IGNORECASE),
    re.compile(r"GPL.*removed", re.IGNORECASE),
    re.compile(r"GPL.*replaced", re.IGNORECASE),
    re.compile(r"GPL.*LGPL.*AGPL.*prohibit", re.IGNORECASE),
    re.compile(r"Placeholder", re.IGNORECASE),
    re.compile(r"re\.compile", re.IGNORECASE),
]
SELF_SCRIPT = "license_audit.py"
FALSE_POSITIVE_PKGS = {"pillow-heif", "pillow_heif"}
KNOWN_BAD_REQUIREMENTS = {"pymupdf", "fitz", "mutagen", "fpdf2", "py7zr", "chardet", "odfpy", "weasyprint", "scancode-toolkit"}
LICENSE_FILE_NAMES = {"license", "license.txt", "license.md", "copying", "copying.txt"}
GPL_LICENSE_RE = re.compile(r"(GNU General Public License|GNU Lesser General Public)", re.IGNORECASE)
