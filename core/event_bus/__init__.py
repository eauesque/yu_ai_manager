"""Event bus singleton and convenience helpers."""

from .bus import EventBus
from .event_types import Event

event_bus = EventBus()


def emit(event_type: str, data: dict | None = None, source: str = "") -> None:
    """Convenience: create an Event and emit it on the global bus."""
    event_bus.emit(Event(type=event_type, data=data or {}, source=source))
