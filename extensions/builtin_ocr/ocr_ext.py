from quart import Blueprint


def get_blueprint():
    return Blueprint("ocr_shim", __name__)


__all__ = ["get_blueprint"]
