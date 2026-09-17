"""builtin-lora-dataset-manager Extension entrypoint."""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from .core_impl.api import create_lora_dataset_blueprint  # noqa: E402
from .core_impl.migrate import on_db_migrate  # noqa: E402, F401


def get_blueprint():
    return create_lora_dataset_blueprint(__name__)


__all__ = ["get_blueprint", "on_db_migrate"]
