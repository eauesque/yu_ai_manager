"""Sidecar text helpers for legacy media metadata parsing."""

from pathlib import Path


def read_sidecar_txt(image_path: Path) -> str | None:
    txt = image_path.with_suffix(image_path.suffix + ".txt")
    if not txt.exists():
        txt = image_path.with_suffix(".txt")
    if not txt.exists():
        return None
    try:
        return txt.read_text(encoding="utf-8", errors="ignore").strip()
    except Exception:
        return None
