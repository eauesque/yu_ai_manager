"""builtin-trophy Extension entrypoint."""

from quart import Blueprint


def get_blueprint():
    return Blueprint("trophy_shim", __name__)


__all__ = ["get_blueprint"]
