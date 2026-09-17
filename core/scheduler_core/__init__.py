"""Task scheduler public API.

Exposes a singleton SchedulerManager for use across the application.
"""

from .scheduler import SchedulerManager

scheduler_manager = SchedulerManager()

__all__ = ["scheduler_manager"]
