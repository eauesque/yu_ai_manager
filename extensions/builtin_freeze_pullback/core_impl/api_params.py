"""Request parameter helpers for Freeze & Pull-back routes."""

from __future__ import annotations

import logging

from .validation import RenderParams, Waypoint

logger = logging.getLogger(__name__)


def build_params(body: dict) -> RenderParams:
    """Build RenderParams from the request body."""
    params = RenderParams()
    params.file_id = int(body.get("file_id", 0))
    params.image_path = body.get("image_path", "")
    params.hold_seconds = float(body.get("hold_seconds", params.hold_seconds))
    params.pull_seconds = float(body.get("pull_seconds", params.pull_seconds))
    params.fps = int(body.get("fps", params.fps))
    params.scale_start = float(body.get("scale_start", params.scale_start))
    params.scale_end = float(body.get("scale_end", params.scale_end))
    params.out_width = int(body.get("out_width", params.out_width))
    params.out_height = int(body.get("out_height", params.out_height))
    params.easing = body.get("easing", params.easing)
    vignette = body.get("vignette", params.vignette)
    if not isinstance(vignette, bool):
        raise ValueError("vignette must be a boolean")
    params.vignette = vignette
    params.direction = body.get("direction", params.direction)
    params.output_format = body.get("output_format", params.output_format)
    params.focus_provider = body.get("focus_provider", params.focus_provider)

    focus_start = body.get("focus_start")
    if isinstance(focus_start, (list, tuple)) and len(focus_start) == 2:
        params.focus_start = (float(focus_start[0]), float(focus_start[1]))

    focus_end = body.get("focus_end")
    if isinstance(focus_end, (list, tuple)) and len(focus_end) == 2:
        params.focus_end = (float(focus_end[0]), float(focus_end[1]))

    raw_waypoints = body.get("waypoints")
    if isinstance(raw_waypoints, list) and raw_waypoints:
        waypoints = []
        for raw in raw_waypoints:
            if not isinstance(raw, dict):
                continue
            waypoints.append(
                Waypoint(
                    x=float(raw.get("x", 0.5)),
                    y=float(raw.get("y", 0.5)),
                    scale=float(raw.get("scale", 2.0)),
                    dwell=float(raw.get("dwell", 1.5)),
                    transition=float(raw.get("transition", 2.0)),
                    easing=raw.get("easing", "ease_in_out_cubic"),
                )
            )
        if waypoints:
            params.waypoints = waypoints

    return params


def apply_source_resolution(params: RenderParams) -> None:
    """Fill out_width/out_height with source image resolution when they are 0."""
    from .validation import OUT_H_DEFAULT, OUT_H_MAX, OUT_W_DEFAULT, OUT_W_MAX

    width, height = 0, 0

    if params.file_id > 0:
        try:
            from core.services_core.db_api import get_readonly_db

            con = get_readonly_db()
            row = con.execute(
                "SELECT width, height FROM files WHERE id = ? AND is_deleted = 0",
                (params.file_id,),
            ).fetchone()
            if row and row[0] and row[1]:
                width, height = row[0], row[1]
        except Exception:
            logger.debug("stored dimensions unavailable for %s", params.file_id, exc_info=True)

    if (width == 0 or height == 0) and params.image_path:
        try:
            from PIL import Image

            with Image.open(params.image_path) as img:
                width, height = img.size
        except OSError as exc:
            logger.warning("Failed to read image dimensions: %s", exc)

    if width > 0 and height > 0:
        width = min(width, OUT_W_MAX) & ~1
        height = min(height, OUT_H_MAX) & ~1
        if params.out_width == 0:
            params.out_width = width if width >= 256 else OUT_W_DEFAULT
        if params.out_height == 0:
            params.out_height = height if height >= 256 else OUT_H_DEFAULT
    else:
        if params.out_width == 0:
            params.out_width = OUT_W_DEFAULT
        if params.out_height == 0:
            params.out_height = OUT_H_DEFAULT
