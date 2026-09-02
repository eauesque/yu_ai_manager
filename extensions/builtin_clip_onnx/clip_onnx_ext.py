"""builtin-clip-onnx Extension entrypoint."""

from quart import Blueprint


def get_blueprint():
    return Blueprint("clip_onnx_shim", __name__)


__all__ = ["get_blueprint"]
