"""builtin-sd-nai-convert Extension entrypoint."""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from .core_impl.sd_nai_convert_api import create_sd_nai_convert_blueprint  # noqa: E402
from .core_impl.sd_nai_convert_engine import convert_nai_to_sd, convert_sd_to_nai  # noqa: E402


def get_blueprint():
    return create_sd_nai_convert_blueprint(__name__)


__all__ = [
    "convert_sd_to_nai",
    "convert_nai_to_sd",
    "get_blueprint",
]
