"""WaypointProvider for multi-waypoint camera path traversal.

Splits timeline into dwell/transition segments and interpolates
focus position with easing for each frame.
"""

from __future__ import annotations

from dataclasses import dataclass

from .focus_provider import (
    FocusContext,
    FocusProvider,
    FocusState,
    FocusStatus,
    get_easing,
)


@dataclass
class _Segment:
    """A single segment on the timeline (dwell or transition)."""

    start_time: float   # Segment start time (seconds)
    end_time: float     # Segment end time (seconds)
    is_dwell: bool      # True = dwell, False = transition
    wp_index: int       # Corresponding waypoint index
    # Transition segments only: source waypoint index
    from_wp_index: int = 0
    easing: str = "ease_in_out_cubic"


class WaypointProvider(FocusProvider):
    """Camera path provider that traverses multiple waypoints.

    Splits timeline into dwell/transition segments and returns
    interpolated positions for each frame.
    """

    def __init__(self, waypoints: list):
        """Initialize with waypoint list.

        Args:
            waypoints: List of Waypoint objects (2 or more)
        """
        self._waypoints: list = waypoints
        self._segments: list = []
        self._total_seconds: float = 0.0
        self._build_segments()

    def _build_segments(self) -> None:
        """Build timeline segments from waypoint list."""
        t = 0.0
        wps = self._waypoints

        for i, wp in enumerate(wps):
            # Non-first WP: transition segment from prev WP to current WP
            if i > 0:
                seg = _Segment(
                    start_time=t,
                    end_time=t + wp.transition,
                    is_dwell=False,
                    wp_index=i,
                    from_wp_index=i - 1,
                    easing=wp.easing,
                )
                self._segments.append(seg)
                t += wp.transition

            # Dwell segment (only when dwell > 0)
            if wp.dwell > 0:
                seg = _Segment(
                    start_time=t,
                    end_time=t + wp.dwell,
                    is_dwell=True,
                    wp_index=i,
                )
                self._segments.append(seg)
                t += wp.dwell

        self._total_seconds = t

    @property
    def total_seconds(self) -> float:
        """Total duration of the waypoint path in seconds."""
        return self._total_seconds

    def init(self, ctx: FocusContext) -> None:
        """Initialize with context (not needed for WaypointProvider, ABC compliance)."""
        pass

    def get_focus(self, t: float) -> FocusState:
        """Return focus state at normalized time t (0..1).

        The scale field contains the zoom factor from waypoints.
        """
        t_clamped = max(0.0, min(1.0, t))

        # Convert time to seconds
        abs_time = t_clamped * self._total_seconds

        # Search for corresponding segment
        seg = self._find_segment(abs_time)
        if seg is None:
            # Fallback: last waypoint
            last = self._waypoints[-1]
            return FocusState(
                center=(last.x, last.y),
                confidence=1.0,
                status=FocusStatus.OK,
                scale=last.scale,
            )

        if seg.is_dwell:
            # Dwell segment: fix coordinates at that waypoint
            wp = self._waypoints[seg.wp_index]
            return FocusState(
                center=(wp.x, wp.y),
                confidence=1.0,
                status=FocusStatus.OK,
                scale=wp.scale,
            )
        else:
            # Transition segment: easing interpolation from prev WP to current WP
            wp_from = self._waypoints[seg.from_wp_index]
            wp_to = self._waypoints[seg.wp_index]

            seg_duration = seg.end_time - seg.start_time
            local_t = 1.0 if seg_duration <= 0 else (abs_time - seg.start_time) / seg_duration
            local_t = max(0.0, min(1.0, local_t))

            ease_fn = get_easing(seg.easing)
            e = ease_fn(local_t)

            cx = wp_from.x + (wp_to.x - wp_from.x) * e
            cy = wp_from.y + (wp_to.y - wp_from.y) * e
            scale = wp_from.scale + (wp_to.scale - wp_from.scale) * e

            return FocusState(
                center=(cx, cy),
                confidence=1.0,
                status=FocusStatus.OK,
                scale=scale,
            )

    def _find_segment(self, abs_time: float) -> _Segment | None:
        """Find the segment corresponding to the given absolute time."""
        for seg in self._segments:
            if seg.start_time <= abs_time < seg.end_time:
                return seg
        # Last frame (t == total_seconds) -> last segment
        if self._segments and abs_time >= self._segments[-1].start_time:
            return self._segments[-1]
        return None
