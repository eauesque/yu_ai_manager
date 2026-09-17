"""builtin-backup Extension entrypoint."""

from quart import Blueprint


def get_blueprint():
    return Blueprint("backup_shim", __name__)


__all__ = ["get_blueprint"]
