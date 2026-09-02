"""Sidecar JSON metadata management.

Records generated video parameters and focus information in a JSON file.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Default output directory
DEFAULT_OUTPUT_DIR = os.path.join("exports", "freeze_pullback")


@dataclass
class SidecarMetadata:
    """Contents of the sidecar JSON."""

    source_file_id: int = 0
    source_path: str = ""
    output_file: str = ""
    created_at: float = 0.0
    duration_seconds: float = 0.0
    hold_seconds: float = 0.0
    pull_seconds: float = 0.0
    fps: int = 30
    scale_start: float = 2.0
    scale_end: float = 1.0
    out_width: int = 1280
    out_height: int = 720
    focus_start: list[float] = field(default_factory=lambda: [0.5, 0.5])
    focus_end: list[float] | None = None
    easing: str = "ease_in_out_cubic"
    vignette: bool = False
    direction: str = "zoom_out"
    output_format: str = "mp4"
    focus_provider_type: str = "StaticProvider"
    elapsed_seconds: float = 0.0
    waypoints: list[dict[str, Any]] | None = None


def write_sidecar(video_path: str, meta: SidecarMetadata) -> str:
    """Write the sidecar JSON corresponding to a video file.

    Returns:
        Path to the sidecar JSON
    """
    sidecar_path = _sidecar_path(video_path)
    data = asdict(meta)
    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return sidecar_path


def read_sidecar(video_path: str) -> dict[str, Any] | None:
    """Read the sidecar JSON."""
    sidecar_path = _sidecar_path(video_path)
    if not os.path.isfile(sidecar_path):
        return None
    try:
        with open(sidecar_path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("sidecar read error %s: %s", sidecar_path, exc)
        return None


_OUTPUT_EXTENSIONS = (".mp4", ".gif", ".png", ".webp", ".webm")


def list_outputs(output_dir: str | None = None) -> list[dict[str, Any]]:
    """Return a list of videos/animations in the output directory."""
    d = output_dir or DEFAULT_OUTPUT_DIR
    if not os.path.isdir(d):
        return []
    results = []
    for name in sorted(os.listdir(d), reverse=True):
        # Target only fpb_ prefix and supported extensions
        if not name.startswith("fpb_"):
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext not in _OUTPUT_EXTENSIONS:
            continue
        video_path = os.path.join(d, name)
        sidecar = read_sidecar(video_path)
        entry: dict[str, Any] = {
            "filename": name,
            "size_bytes": os.path.getsize(video_path),
            "created_at": sidecar.get("created_at", 0) if sidecar else 0,
            "format": sidecar.get("output_format", "mp4") if sidecar else ext.lstrip("."),
        }
        if sidecar:
            entry["duration"] = sidecar.get("duration_seconds", 0)
            entry["source_file_id"] = sidecar.get("source_file_id", 0)
        results.append(entry)
    return results


def ensure_output_dir(output_dir: str | None = None) -> str:
    """Create and return the output directory."""
    d = output_dir or DEFAULT_OUTPUT_DIR
    os.makedirs(d, exist_ok=True)
    return d


def _sidecar_path(video_path: str) -> str:
    """Generate sidecar JSON path from video path."""
    base, _ = os.path.splitext(video_path)
    return base + ".json"
