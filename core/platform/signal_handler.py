"""Signal handler registration placeholder.

Signal handling is now managed by ``core.web.shutdown`` which installs
SIGINT/SIGTERM handlers that trigger graceful shutdown with a watchdog.

This module is kept for backward compatibility — ``install_sigint_handler``
is a no-op since shutdown.py handles everything.
"""


def install_sigint_handler() -> None:
    """No-op: signal handling is managed by core.web.shutdown."""
    pass
