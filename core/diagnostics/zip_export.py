"""Zip export for diagnostics repair directories."""

from __future__ import annotations

import zipfile
from pathlib import Path


def zip_repair_dir(repair_dir: Path) -> Path:
    root = repair_dir.resolve()
    if not root.is_dir():
        raise FileNotFoundError(str(root))
    zip_path = root.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(root).as_posix())
    return zip_path
