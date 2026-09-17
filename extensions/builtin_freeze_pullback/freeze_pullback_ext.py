"""Freeze & Pull-back Generator extension entrypoint."""

from .core_impl.api import create_fpb_blueprint


def get_blueprint():
    """Entrypoint called by the extension loader."""
    return create_fpb_blueprint(__name__)
