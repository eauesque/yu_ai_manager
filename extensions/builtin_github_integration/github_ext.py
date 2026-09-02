import logging

logger = logging.getLogger(__name__)
"""builtin-github-integration Extension entrypoint."""



def get_blueprint():
    from .core_impl.api import bp
    # Register GitHub account tokens in the settings schema
    # so they appear in Settings > Secrets alongside other API keys.
    try:
        from .core_impl.account_store import sync_token_settings
        sync_token_settings()
    except Exception:
        logger.debug("token settings sync unavailable at import time", exc_info=True)
    return bp


__all__ = ["get_blueprint"]
