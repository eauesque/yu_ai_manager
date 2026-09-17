"""Rendering parameter validation.

Defines hard limit constants and the RenderParams dataclass.
"""

from __future__ import annotations

from dataclasses import dataclass

# ── Waypoint constants ─────────────────────────────────
WAYPOINT_MIN_COUNT = 2
WAYPOINT_SCALE_MIN = 1.0
WAYPOINT_SCALE_MAX = 5.0
WAYPOINT_DWELL_MIN = 0.0
WAYPOINT_DWELL_MAX = 10.0
WAYPOINT_TRANSITION_MIN = 0.5
WAYPOINT_TRANSITION_MAX = 10.0


# ── Hard limit constants ───────────────────────────────────

HOLD_SEC_MIN = 1.0
HOLD_SEC_MAX = 10.0
HOLD_SEC_DEFAULT = 2.0

PULL_SEC_MIN = 1.0
PULL_SEC_MAX = 20.0
PULL_SEC_DEFAULT = 5.0

DURATION_MIN = 2.0
DURATION_MAX = 30.0

FPS_MIN = 15
FPS_MAX = 60
FPS_DEFAULT = 30

SCALE_START_MIN = 1.2
SCALE_START_MAX = 5.0
SCALE_START_DEFAULT = 2.0

SCALE_END_MIN = 1.0
SCALE_END_DEFAULT = 1.0

DIRECTION_ZOOM_OUT = "zoom_out"
DIRECTION_ZOOM_IN = "zoom_in"
DIRECTION_DEFAULT = DIRECTION_ZOOM_OUT
VALID_DIRECTIONS = (DIRECTION_ZOOM_OUT, DIRECTION_ZOOM_IN)

FORMAT_MP4 = "mp4"
FORMAT_GIF = "gif"
FORMAT_APNG = "apng"
FORMAT_WEBP = "webp"
FORMAT_WEBM = "webm"
FORMAT_DEFAULT = FORMAT_MP4
VALID_FORMATS = (FORMAT_MP4, FORMAT_GIF, FORMAT_APNG, FORMAT_WEBP, FORMAT_WEBM)

# Extensions per format
FORMAT_EXT = {
    FORMAT_MP4: ".mp4",
    FORMAT_GIF: ".gif",
    FORMAT_APNG: ".png",
    FORMAT_WEBP: ".webp",
    FORMAT_WEBM: ".webm",
}

# MIME types per format
FORMAT_MIME = {
    FORMAT_MP4: "video/mp4",
    FORMAT_GIF: "image/gif",
    FORMAT_APNG: "image/png",
    FORMAT_WEBP: "image/webp",
    FORMAT_WEBM: "video/webm",
}

OUT_W_MIN = 256
OUT_W_MAX = 3840
OUT_W_DEFAULT = 1280

OUT_H_MIN = 256
OUT_H_MAX = 2160
OUT_H_DEFAULT = 720


@dataclass
class Waypoint:
    """A single point on a multi-point camera path."""

    x: float = 0.5            # Focus x (normalized coordinate 0-1)
    y: float = 0.5            # Focus y (normalized coordinate 0-1)
    scale: float = 2.0        # Zoom factor
    dwell: float = 1.5        # Dwell time at this point (seconds)
    transition: float = 2.0   # Transition time from previous WP (seconds). Ignored for first WP
    easing: str = "ease_in_out_cubic"  # Transition easing


@dataclass
class RenderParams:
    """Video rendering parameters."""

    file_id: int = 0
    image_path: str = ""
    hold_seconds: float = HOLD_SEC_DEFAULT
    pull_seconds: float = PULL_SEC_DEFAULT
    fps: int = FPS_DEFAULT
    scale_start: float = SCALE_START_DEFAULT
    scale_end: float = SCALE_END_DEFAULT
    out_width: int = OUT_W_DEFAULT
    out_height: int = OUT_H_DEFAULT
    focus_start: tuple[float, float] = (0.5, 0.5)
    focus_end: tuple[float, float] | None = None
    easing: str = "ease_in_out_cubic"
    vignette: bool = False
    direction: str = DIRECTION_DEFAULT
    output_format: str = FORMAT_DEFAULT
    focus_provider: str = "static"
    waypoints: list[Waypoint] | None = None


def validate_params(p: RenderParams) -> list[str]:
    """Validate RenderParams and return a list of error messages.

    Returns an empty list if there are no errors.
    """
    errors: list[str] = []

    if not p.image_path and p.file_id <= 0:
        errors.append("file_id or image_path is required")

    # ── Waypoint mode ──
    if p.waypoints:
        errors.extend(_validate_waypoints(p.waypoints))
    else:
        # ── Legacy mode: hold/pull/scale validation ──
        # hold_seconds
        if p.hold_seconds < HOLD_SEC_MIN or p.hold_seconds > HOLD_SEC_MAX:
            errors.append(
                f"hold_seconds must be {HOLD_SEC_MIN}-{HOLD_SEC_MAX}, got {p.hold_seconds}"
            )

        # pull_seconds
        if p.pull_seconds < PULL_SEC_MIN or p.pull_seconds > PULL_SEC_MAX:
            errors.append(
                f"pull_seconds must be {PULL_SEC_MIN}-{PULL_SEC_MAX}, got {p.pull_seconds}"
            )

        # Total duration
        total = p.hold_seconds + p.pull_seconds
        if total < DURATION_MIN or total > DURATION_MAX:
            errors.append(
                f"total duration must be {DURATION_MIN}-{DURATION_MAX}s, got {total:.1f}s"
            )

        # direction
        if p.direction not in VALID_DIRECTIONS:
            errors.append(
                f"direction must be one of {VALID_DIRECTIONS}, got '{p.direction}'"
            )

        # scale
        start_min = SCALE_END_MIN if p.direction == DIRECTION_ZOOM_IN else SCALE_START_MIN
        if p.scale_start < start_min or p.scale_start > SCALE_START_MAX:
            errors.append(
                f"scale_start must be {start_min}-{SCALE_START_MAX}, got {p.scale_start}"
            )
        if p.scale_end < SCALE_END_MIN:
            errors.append(f"scale_end must be >= {SCALE_END_MIN}, got {p.scale_end}")
        if p.scale_end > SCALE_START_MAX:
            errors.append(f"scale_end must be <= {SCALE_START_MAX}, got {p.scale_end}")

        if p.direction == DIRECTION_ZOOM_OUT:
            if p.scale_end >= p.scale_start:
                errors.append(
                    f"zoom_out: scale_end ({p.scale_end}) must be < scale_start ({p.scale_start})"
                )
        elif p.direction == DIRECTION_ZOOM_IN and p.scale_end <= p.scale_start:
            errors.append(
                f"zoom_in: scale_end ({p.scale_end}) must be > scale_start ({p.scale_start})"
            )

        # Focus coordinates
        for label, coord in [("focus_start", p.focus_start)]:
            if coord and not (0.0 <= coord[0] <= 1.0 and 0.0 <= coord[1] <= 1.0):
                errors.append(f"{label} coordinates must be 0.0-1.0")
        if p.focus_end and not (0.0 <= p.focus_end[0] <= 1.0 and 0.0 <= p.focus_end[1] <= 1.0):
            errors.append("focus_end coordinates must be 0.0-1.0")

        # easing
        from .focus_provider import EASING_FUNCTIONS
        if p.easing not in EASING_FUNCTIONS:
            errors.append(
                f"unknown easing: '{p.easing}', valid: {', '.join(EASING_FUNCTIONS)}"
            )

    # ── Common validation ──

    # fps
    if p.fps < FPS_MIN or p.fps > FPS_MAX:
        errors.append(f"fps must be {FPS_MIN}-{FPS_MAX}, got {p.fps}")

    # output_format
    if p.output_format not in VALID_FORMATS:
        errors.append(
            f"output_format must be one of {VALID_FORMATS}, got '{p.output_format}'"
        )

    # output size
    if p.out_width < OUT_W_MIN or p.out_width > OUT_W_MAX:
        errors.append(f"out_width must be {OUT_W_MIN}-{OUT_W_MAX}, got {p.out_width}")
    if p.out_height < OUT_H_MIN or p.out_height > OUT_H_MAX:
        errors.append(f"out_height must be {OUT_H_MIN}-{OUT_H_MAX}, got {p.out_height}")

    return errors


def _validate_waypoints(waypoints: list[Waypoint]) -> list[str]:
    """Validate the waypoint list."""
    from .focus_provider import EASING_FUNCTIONS

    errors: list[str] = []

    if len(waypoints) < WAYPOINT_MIN_COUNT:
        errors.append(
            f"waypoints must have at least {WAYPOINT_MIN_COUNT} points, got {len(waypoints)}"
        )
        return errors

    total_duration = 0.0
    for idx, wp in enumerate(waypoints):
        prefix = f"waypoints[{idx}]"

        # Coordinates
        if not (0.0 <= wp.x <= 1.0):
            errors.append(f"{prefix}.x must be 0.0-1.0, got {wp.x}")
        if not (0.0 <= wp.y <= 1.0):
            errors.append(f"{prefix}.y must be 0.0-1.0, got {wp.y}")

        # scale
        if wp.scale < WAYPOINT_SCALE_MIN or wp.scale > WAYPOINT_SCALE_MAX:
            errors.append(
                f"{prefix}.scale must be {WAYPOINT_SCALE_MIN}-{WAYPOINT_SCALE_MAX}, got {wp.scale}"
            )

        # dwell
        if wp.dwell < WAYPOINT_DWELL_MIN or wp.dwell > WAYPOINT_DWELL_MAX:
            errors.append(
                f"{prefix}.dwell must be {WAYPOINT_DWELL_MIN}-{WAYPOINT_DWELL_MAX}, got {wp.dwell}"
            )

        # transition (ignored for first WP)
        if idx > 0:
            if wp.transition < WAYPOINT_TRANSITION_MIN or wp.transition > WAYPOINT_TRANSITION_MAX:
                errors.append(
                    f"{prefix}.transition must be {WAYPOINT_TRANSITION_MIN}-{WAYPOINT_TRANSITION_MAX}, got {wp.transition}"
                )
            total_duration += wp.transition

        # easing
        if wp.easing not in EASING_FUNCTIONS:
            errors.append(
                f"{prefix}.easing unknown: '{wp.easing}', valid: {', '.join(EASING_FUNCTIONS)}"
            )

        total_duration += wp.dwell

    # Total duration check
    if total_duration < DURATION_MIN:
        errors.append(
            f"waypoints total duration must be >= {DURATION_MIN}s, got {total_duration:.1f}s"
        )
    if total_duration > DURATION_MAX:
        errors.append(
            f"waypoints total duration must be <= {DURATION_MAX}s, got {total_duration:.1f}s"
        )

    return errors
