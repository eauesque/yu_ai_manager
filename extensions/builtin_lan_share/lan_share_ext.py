"""builtin-lan-share Extension entrypoint."""

from quart import Blueprint


def get_blueprint():
    return Blueprint("lan_share_shim", __name__)


__all__ = ["get_blueprint"]
