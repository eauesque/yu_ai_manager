"""Video renderer.

Generates frames with PIL, pipes RGB24 raw bytes to ffmpeg stdin for H.264 mp4.
ffmpeg command building and vignette effect are in render_ffmpeg.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time

from PIL import Image

from .camera import compute_viewport
from .focus_provider import (
    FocusContext,
    ROIProvider,
    StaticProvider,
    WaypointProvider,
    fallback_focus,
)
from .render_ffmpeg import apply_vignette, build_ffmpeg_cmd

# Re-export for backward compatibility
from .render_ffmpeg import (  # noqa: F401
    apply_vignette as _apply_vignette,
)
from .sidecar import SidecarMetadata, ensure_output_dir, write_sidecar
from .validation import FORMAT_EXT, RenderParams

logger = logging.getLogger(__name__)


def render_video(
    params: RenderParams,
    job=None,
    output_dir: str | None = None,
) -> str:
    """Render a video.

    Args:
        params: Rendering parameters
        job: JobManager Job object (for progress notifications)
        output_dir: Output directory (None = default)

    Returns:
        Path to the output video file

    Raises:
        FileNotFoundError: Source image not found
        RuntimeError: ffmpeg error
    """
    # Open source image
    if not os.path.isfile(params.image_path):
        raise FileNotFoundError(f"Source image not found: {params.image_path}")

    with Image.open(params.image_path) as _raw_img:
        img = _raw_img.convert("RGB")
    img_w, img_h = img.size

    # -- Waypoint mode detection --
    use_waypoints = bool(params.waypoints)

    if use_waypoints:
        # Waypoints mode: use WaypointProvider
        wp_provider = WaypointProvider(params.waypoints)
        total_seconds = wp_provider.total_seconds
        total_frames = max(1, int(total_seconds * params.fps))
        provider_type = wp_provider.provider_type
    else:
        # Legacy mode: FocusProvider setup
        total_seconds = params.hold_seconds + params.pull_seconds
        total_frames = int(total_seconds * params.fps)
        provider_type = None  # Set later

    # FocusProvider setup (for legacy mode)
    provider = None
    fallback_prov = None
    hold_frames = 0
    if not use_waypoints:
        provider, fallback_prov = _setup_providers(params, img_w, img_h)
        hold_frames = int(params.hold_seconds * params.fps)
        provider_type = provider.provider_type

    # Output filename
    out_dir = ensure_output_dir(output_dir)
    timestamp = int(time.time())
    ext = FORMAT_EXT.get(params.output_format, ".mp4")
    filename = f"fpb_{params.file_id}_{timestamp}{ext}"
    output_path = os.path.join(out_dir, filename)

    if job:
        job.update(phase="rendering", message="Rendering frames...")
        job.progress(0, total_frames)

    # Launch ffmpeg process
    cmd = build_ffmpeg_cmd(params, output_path)
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    render_start = time.time()

    try:
        for i in range(total_frames):
            # Cancel check
            if job and job.cancelled:
                proc.stdin.close()
                proc.terminate()
                proc.wait(timeout=5)
                # Delete incomplete file
                if os.path.isfile(output_path):
                    os.remove(output_path)
                return ""

            if use_waypoints:
                # -- Waypoint mode --
                t_norm = i / max(1, total_frames - 1)
                focus = wp_provider.get_focus(t_norm)

                # Use the scale returned by WaypointProvider as-is
                current_scale = focus.scale if focus.scale is not None else 1.0
                vp = compute_viewport(
                    t=0.0,
                    focus_x=focus.center[0],
                    focus_y=focus.center[1],
                    img_w=img_w,
                    img_h=img_h,
                    out_w=params.out_width,
                    out_h=params.out_height,
                    scale_start=current_scale,
                    scale_end=current_scale,
                    easing="linear",
                )
            else:
                # -- Legacy mode --
                if i < hold_frames:
                    # Hold phase: static at scale_start
                    t_focus = 0.0
                    t_scale = 0.0
                else:
                    # Pullback phase: scale_start -> scale_end
                    pull_progress = (i - hold_frames) / max(1, total_frames - hold_frames - 1)
                    t_focus = pull_progress
                    t_scale = pull_progress

                # Get focus position
                focus = fallback_focus(provider, fallback_prov, t_focus)

                # Calculate viewport
                vp = compute_viewport(
                    t=t_scale,
                    focus_x=focus.center[0],
                    focus_y=focus.center[1],
                    img_w=img_w,
                    img_h=img_h,
                    out_w=params.out_width,
                    out_h=params.out_height,
                    scale_start=params.scale_start,
                    scale_end=params.scale_end,
                    easing=params.easing,
                )

            # Generate frame (crop + resize)
            frame = img.crop((vp.x, vp.y, vp.x + vp.w, vp.y + vp.h))
            frame = frame.resize(
                (params.out_width, params.out_height), Image.LANCZOS
            )

            # Vignette (optional)
            if params.vignette:
                frame = apply_vignette(frame)

            # Send to ffmpeg
            proc.stdin.write(frame.tobytes())

            # Progress notification
            if job and (i % max(1, total_frames // 50) == 0 or i == total_frames - 1):
                job.progress(i + 1, total_frames, f"Frame {i + 1}/{total_frames}")

        proc.stdin.close()
        _, stderr = proc.communicate(timeout=30)

        if proc.returncode != 0:
            err_msg = stderr.decode("utf-8", errors="ignore")[:500]
            raise RuntimeError(f"ffmpeg exited with code {proc.returncode}: {err_msg}")

    except Exception:
        proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=5)
        if os.path.isfile(output_path):
            os.remove(output_path)
        raise

    elapsed = time.time() - render_start

    # Convert waypoint info to dict list (for sidecar)
    waypoints_dict = None
    if use_waypoints and params.waypoints:
        from dataclasses import asdict
        waypoints_dict = [asdict(wp) for wp in params.waypoints]

    # Write sidecar
    meta = SidecarMetadata(
        source_file_id=params.file_id,
        source_path=params.image_path,
        output_file=filename,
        created_at=time.time(),
        duration_seconds=total_seconds,
        hold_seconds=params.hold_seconds if not use_waypoints else 0.0,
        pull_seconds=params.pull_seconds if not use_waypoints else 0.0,
        fps=params.fps,
        scale_start=params.scale_start if not use_waypoints else 0.0,
        scale_end=params.scale_end if not use_waypoints else 0.0,
        out_width=params.out_width,
        out_height=params.out_height,
        focus_start=list(params.focus_start) if not use_waypoints else [0.5, 0.5],
        focus_end=list(params.focus_end) if (not use_waypoints and params.focus_end) else None,
        easing=params.easing if not use_waypoints else "",
        vignette=params.vignette,
        direction=params.direction if not use_waypoints else "",
        output_format=params.output_format,
        focus_provider_type=provider_type,
        elapsed_seconds=round(elapsed, 2),
        waypoints=waypoints_dict,
    )
    write_sidecar(output_path, meta)

    return output_path


def _setup_providers(params: RenderParams, img_w: int, img_h: int):
    """Initialize FocusProvider and fallback."""
    ctx = FocusContext(
        image_width=img_w,
        image_height=img_h,
        focus_start=params.focus_start,
        focus_end=params.focus_end,
    )

    # StaticProvider is always prepared as fallback
    fallback = StaticProvider(easing=params.easing)
    fallback.init(ctx)

    if params.focus_provider == "roi":
        provider = ROIProvider(easing=params.easing)
    else:
        provider = StaticProvider(easing=params.easing)

    provider.init(ctx)
    return provider, fallback
