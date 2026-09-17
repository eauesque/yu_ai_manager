"""builtin-wd-tagger Extension entrypoint."""

from quart import Blueprint


def get_blueprint():
    return Blueprint("wd_tagger_shim", __name__)


__all__ = ["get_blueprint"]
