"""Python syntax diagnostics."""

import ast
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


PY_GLOBS = ["*.py", "core/*.py", "routes/*.py", "cli/*.py", "extensions/**/*.py"]


def _collect_syntax_errors() -> tuple[int, list[tuple[str, SyntaxError]]]:
    count = 0
    errors: list[tuple[str, SyntaxError]] = []
    for pattern in PY_GLOBS:
        for f in Path(".").glob(pattern):
            if "__pycache__" in str(f):
                continue
            count += 1
            try:
                ast.parse(f.read_text(encoding="utf-8"))
            except SyntaxError as e:
                errors.append((str(f), e))
    return count, errors


def check_syntax() -> None:
    """Check Python source syntax in key directories."""
    logger.info("=== Syntax Check ===")
    count, errors = _collect_syntax_errors()
    if errors:
        for path, err in errors:
            logger.error(f"  {path}: {err}")
    else:
        logger.info(f"  {count} files all OK")
