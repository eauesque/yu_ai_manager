"""builtin-debug-check Extension entrypoint."""

from quart import Blueprint


def get_blueprint():
    return Blueprint("debug_check_shim", __name__)


__all__ = ["get_blueprint"]
