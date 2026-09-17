"""builtin-clip-coreml Extension entrypoint."""

from quart import Blueprint


def get_blueprint():
    return Blueprint("clip_coreml_shim", __name__)


__all__ = ["get_blueprint"]
