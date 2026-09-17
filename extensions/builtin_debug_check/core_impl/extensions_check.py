"""Extensions diagnostics."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def check_extensions() -> None:
    """Inspect extension directory and manifest presence."""
    logger.info("\n=== Extension Check ===")
    ext_dir = Path("extensions")
    if not ext_dir.exists():
        logger.info("  [!] extensions/ directory not found")
        return

    for d in sorted(ext_dir.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        manifest = None
        for name in ["extension.json", "extension.yml", "manifest.json"]:
            if (d / name).exists():
                manifest = name
                break
        status = f"[OK] {manifest}" if manifest else "[NG] no manifest"
        has_py = any(d.glob("*.py"))
        logger.info(f"  {d.name}: {status} {'(py)' if has_py else '[!] no .py'}")
