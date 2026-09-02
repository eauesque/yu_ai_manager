"""YOLO HEF model download and status management.

Downloads pre-compiled HEF files from the Hailo Model Zoo v5.2.0
for use with Hailo-10H.
"""

import logging
import os
from pathlib import Path
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_DEFAULT_HEF_DIR = os.environ.get("HAILO_HEF_DIR", str(Path.home() / "hailo_models"))
_BASE_URL = "https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h"

YOLO_MODELS = {
    "yolov8n": {
        "filename": "yolov8n.hef",
        "url": f"{_BASE_URL}/yolov8n.hef",
        "input_size": 640,
        "description": "YOLOv8 Nano (mAP 36.4, fastest)",
    },
    "yolov11n": {
        "filename": "yolov11n.hef",
        "url": f"{_BASE_URL}/yolov11n.hef",
        "input_size": 640,
        "description": "YOLOv11 Nano (mAP 37.9)",
    },
    "yolov5m": {
        "filename": "yolov5m_wo_spp.hef",
        "url": f"{_BASE_URL}/yolov5m_wo_spp.hef",
        "input_size": 640,
        "description": "YOLOv5 Medium (mAP 41.4, most accurate)",
    },
}

_USER_AGENT = "YU-AI-Manager/2.55 (Hailo Model Download)"


def get_hef_path(model_name: str, hef_dir: str | None = None) -> Path:
    """Return the expected local path for a model HEF."""
    hef_dir = hef_dir or _DEFAULT_HEF_DIR
    info = YOLO_MODELS.get(model_name)
    if not info:
        raise ValueError(f"Unknown YOLO model: {model_name}")
    return Path(hef_dir) / info["filename"]


def is_hef_available(model_name: str, hef_dir: str | None = None) -> bool:
    """Check if a HEF file exists locally."""
    try:
        return get_hef_path(model_name, hef_dir).exists()
    except ValueError:
        return False


def get_model_status(hef_dir: str | None = None) -> dict:
    """Return availability status for all YOLO models."""
    result = {}
    for name, info in YOLO_MODELS.items():
        path = get_hef_path(name, hef_dir)
        result[name] = {
            "available": path.exists(),
            "path": str(path),
            "description": info["description"],
            "input_size": info["input_size"],
            "file_size_mb": round(path.stat().st_size / 1024 / 1024, 1) if path.exists() else None,
        }
    return result


def download_hef(
    model_name: str,
    hef_dir: str | None = None,
    progress_callback=None,
) -> Path:
    """Download a YOLO HEF from the Hailo Model Zoo.

    Args:
        model_name: key in YOLO_MODELS
        hef_dir: target directory (default ~/hailo_models)
        progress_callback: optional fn(downloaded_bytes, total_bytes)

    Returns:
        Path to the downloaded HEF file

    Raises:
        ValueError: unknown model name
        OSError: download failure
    """
    info = YOLO_MODELS.get(model_name)
    if not info:
        raise ValueError(f"Unknown YOLO model: {model_name}")

    hef_dir = hef_dir or _DEFAULT_HEF_DIR
    os.makedirs(hef_dir, exist_ok=True)
    target = Path(hef_dir) / info["filename"]

    if target.exists():
        logger.info("HEF already exists: %s", target)
        return target

    url = info["url"]
    logger.info("Downloading %s from %s", model_name, url)

    req = Request(url, headers={"User-Agent": _USER_AGENT})
    with urlopen(req, timeout=120) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        tmp_path = target.with_suffix(".hef.tmp")

        with open(tmp_path, "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if progress_callback and total > 0:
                    progress_callback(downloaded, total)

    tmp_path.rename(target)
    size_mb = target.stat().st_size / 1024 / 1024
    logger.info("Downloaded %s (%.1f MB)", target, size_mb)
    return target
