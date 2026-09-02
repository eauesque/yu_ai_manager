"""builtin-sns-share Extension entrypoint."""

from quart import Blueprint


def get_blueprint():
    return Blueprint("sns_share_shim", __name__)


__all__ = ["get_blueprint"]
