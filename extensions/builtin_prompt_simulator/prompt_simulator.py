"""builtin-prompt-simulator Extension entrypoint."""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from .core_impl.prompt_sim_api import create_prompt_simulator_blueprint  # noqa: E402


def get_blueprint():
    return create_prompt_simulator_blueprint(__name__)


__all__ = ["get_blueprint"]
