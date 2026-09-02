"""ffmpeg command builder and vignette effect for video rendering."""

from __future__ import annotations

from PIL import Image, ImageDraw

from .validation import RenderParams


def build_ffmpeg_cmd(params: RenderParams, output_path: str) -> list:
    """Build the ffmpeg command line arguments."""
    # Common input section
    base = [
        "ffmpeg",
        "-y",
        "-f", "rawvideo",
        "-pix_fmt", "rgb24",
        "-s", f"{params.out_width}x{params.out_height}",
        "-r", str(params.fps),
        "-i", "pipe:0",
    ]

    fmt = params.output_format

    if fmt == "gif":
        # High quality GIF with 2-pass palette
        return base + [
            "-vf", "split[s0][s1];[s0]palettegen=max_colors=256[p];[s1][p]paletteuse=dither=sierra2_4a",
            "-loop", "0",
            output_path,
        ]

    if fmt == "apng":
        return base + [
            "-f", "apng",
            "-plays", "0",
            output_path,
        ]

    if fmt == "webp":
        # Animated WebP (lossy, quality 80)
        return base + [
            "-c:v", "libwebp_anim",
            "-quality", "80",
            "-lossless", "0",
            "-loop", "0",
            output_path,
        ]

    if fmt == "webm":
        # VP9 WebM (no audio)
        return base + [
            "-c:v", "libvpx-vp9",
            "-crf", "32",
            "-b:v", "0",
            "-an",
            output_path,
        ]

    # mp4 (default)
    return base + [
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        output_path,
    ]


def apply_vignette(frame: Image.Image) -> Image.Image:
    """Apply a light vignette effect to a frame."""
    w, h = frame.size
    # Semi-transparent black gradient overlay
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    # Darken outside the ellipse
    cx, cy = w // 2, h // 2
    max_r = max(cx, cy) * 1.2
    steps = 20
    for i in range(steps):
        r = max_r * (1.0 - i / steps)
        alpha = int(60 * (i / steps) ** 2)
        draw.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            fill=(0, 0, 0, alpha),
        )
    frame_rgba = frame.convert("RGBA")
    result = Image.alpha_composite(frame_rgba, overlay)
    return result.convert("RGB")
