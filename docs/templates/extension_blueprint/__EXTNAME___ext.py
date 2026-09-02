# docs/templates/extension_blueprint/__EXTNAME___ext.py
"""__EXTNAME__ Extension entrypoint."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from quart import Blueprint  # noqa: E402

from .core_impl import api_mutations, api_queries  # noqa: F401
from .core_impl._blueprint import bp  # noqa: E402

logger = logging.getLogger(__name__)


def get_blueprint() -> Blueprint:
    return bp


__all__ = ["get_blueprint"]
