"""FocusProvider ABC and concrete providers.

FocusProvider is the strategy pattern for determining focus position per frame.
v0 implements StaticProvider (linear/easing interpolation) and ROIProvider.
Future TrackerProvider can be swapped in without core changes.

WaypointProvider is in focus_waypoint module.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum


class FocusStatus(StrEnum):
    """Focus tracking status."""

    OK = "ok"
    DEGRADED = "degraded"
    LOST = "lost"


@dataclass
class FocusState:
    """Focus state at a given time t."""

    center: tuple[float, float]  # (x, y) normalized coordinate 0..1
    confidence: float = 1.0      # 0..1
    status: FocusStatus = FocusStatus.OK
    roi: tuple[float, float, float, float] | None = None  # (x, y, w, h)
    scale: float | None = None  # Scale value for waypoint mode


@dataclass
class FocusContext:
    """Context for FocusProvider initialization."""

    image_width: int
    image_height: int
    focus_start: tuple[float, float] = (0.5, 0.5)
    focus_end: tuple[float, float] | None = None
    roi_start: tuple[float, float, float, float] | None = None
    roi_end: tuple[float, float, float, float] | None = None
    extra: dict = field(default_factory=dict)


# -- Easing functions --------------------------------------------------


def ease_linear(t: float) -> float:
    """Linear interpolation."""
    return t


def ease_in_out_cubic(t: float) -> float:
    """Cubic ease-in-out."""
    if t < 0.5:
        return 4.0 * t * t * t
    p = 2.0 * t - 2.0
    return 0.5 * p * p * p + 1.0


def ease_out_quad(t: float) -> float:
    """Quadratic ease-out."""
    return t * (2.0 - t)


def ease_in_quad(t: float) -> float:
    """Quadratic ease-in."""
    return t * t


def ease_out_expo(t: float) -> float:
    """Exponential ease-out."""
    if t >= 1.0:
        return 1.0
    return 1.0 - math.pow(2.0, -10.0 * t)


EASING_FUNCTIONS = {
    "linear": ease_linear,
    "ease_in_out_cubic": ease_in_out_cubic,
    "ease_out_quad": ease_out_quad,
    "ease_in_quad": ease_in_quad,
    "ease_out_expo": ease_out_expo,
}


def get_easing(name: str):
    """Get easing function by name. Falls back to linear for unknown names."""
    return EASING_FUNCTIONS.get(name, ease_linear)


# -- FocusProvider ABC -------------------------------------------------


class FocusProvider(ABC):
    """Abstract base class for focus position providers."""

    @abstractmethod
    def init(self, ctx: FocusContext) -> None:
        """Initialize with context."""

    @abstractmethod
    def get_focus(self, t: float) -> FocusState:
        """Return focus state at normalized time t (0..1)."""

    @property
    def provider_type(self) -> str:
        return self.__class__.__name__


# -- StaticProvider ----------------------------------------------------


class StaticProvider(FocusProvider):
    """Static provider that interpolates focus_start to focus_end with easing."""

    def __init__(self, easing: str = "ease_in_out_cubic"):
        self._start: tuple[float, float] = (0.5, 0.5)
        self._end: tuple[float, float] = (0.5, 0.5)
        self._ease = get_easing(easing)
        self._easing_name = easing

    def init(self, ctx: FocusContext) -> None:
        self._start = ctx.focus_start
        self._end = ctx.focus_end if ctx.focus_end else ctx.focus_start

    def get_focus(self, t: float) -> FocusState:
        t_clamped = max(0.0, min(1.0, t))
        e = self._ease(t_clamped)
        cx = self._start[0] + (self._end[0] - self._start[0]) * e
        cy = self._start[1] + (self._end[1] - self._start[1]) * e
        return FocusState(
            center=(cx, cy),
            confidence=1.0,
            status=FocusStatus.OK,
        )


# -- ROIProvider -------------------------------------------------------


class ROIProvider(FocusProvider):
    """Provider that uses ROI rectangle center as focus position."""

    def __init__(self, easing: str = "ease_in_out_cubic"):
        self._start_center: tuple[float, float] = (0.5, 0.5)
        self._end_center: tuple[float, float] = (0.5, 0.5)
        self._ease = get_easing(easing)

    def init(self, ctx: FocusContext) -> None:
        if ctx.roi_start:
            x, y, w, h = ctx.roi_start
            self._start_center = (x + w / 2, y + h / 2)
        else:
            self._start_center = ctx.focus_start

        if ctx.roi_end:
            x, y, w, h = ctx.roi_end
            self._end_center = (x + w / 2, y + h / 2)
        elif ctx.focus_end:
            self._end_center = ctx.focus_end
        else:
            self._end_center = self._start_center

    def get_focus(self, t: float) -> FocusState:
        t_clamped = max(0.0, min(1.0, t))
        e = self._ease(t_clamped)
        cx = self._start_center[0] + (self._end_center[0] - self._start_center[0]) * e
        cy = self._start_center[1] + (self._end_center[1] - self._start_center[1]) * e
        return FocusState(
            center=(cx, cy),
            confidence=0.9,
            status=FocusStatus.OK,
        )


# -- Fallback ----------------------------------------------------------


def fallback_focus(
    primary: FocusProvider,
    fallback: StaticProvider,
    t: float,
) -> FocusState:
    """Fall back to fallback provider if primary returns lost status."""
    state = primary.get_focus(t)
    if state.status == FocusStatus.LOST:
        return fallback.get_focus(t)
    return state


# -- Re-export WaypointProvider for backward compatibility --
from .focus_waypoint import WaypointProvider  # noqa: E402, F401
