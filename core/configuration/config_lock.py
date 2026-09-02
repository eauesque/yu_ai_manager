"""Thread lock to prevent read-modify-write races on config files.

Prevents data loss when save_partial_config() etc. are called
concurrently from multiple threads.
"""

import threading

_config_rlock = threading.RLock()


def config_lock():
    """Return the RLock for config read-modify-write protection.

    Usage::

        with config_lock():
            cfg = load_config_json(path)
            cfg["key"] = value
            save_config_json(cfg, path)
    """
    return _config_rlock
