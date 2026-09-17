"""builtin-analysis Extension entrypoint."""

from quart import Blueprint


def get_blueprint():
    return Blueprint("analysis_shim", __name__)


__all__ = ["get_blueprint"]
