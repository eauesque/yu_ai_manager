"""Runtime module import diagnostics."""

import logging

logger = logging.getLogger(__name__)


def check_modules() -> None:
    """Check required/optional Python modules."""
    logger.info("\n=== Module Check ===")
    modules = [
        ("flask", "Flask Web Framework"),
        ("PIL", "Pillow (Image processing)"),
        ("yaml", "PyYAML (YAML config) [optional]"),
    ]
    for mod, desc in modules:
        try:
            __import__(mod)
            logger.info(f"  [OK] {desc}")
        except ImportError:
            optional = "[optional]" in desc
            if optional:
                logger.warning(f"  {desc} -- not installed (optional)")
            else:
                logger.error(f"  {desc} -- not installed")
