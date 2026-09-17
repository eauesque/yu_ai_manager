#!/usr/bin/env python3
"""Diagnose whether an image file has sweep XMP attached.

Usage: uv run python scripts/check_sweep_xmp.py <image_path> [<image_path> ...]

Prints the sweep namespace attrs for each file (or "no sweep XMP" / error).
Use this to verify the Phase 3 write path actually populated the XMP after
a sweep run, independent of the running web server.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running as `uv run python scripts/check_sweep_xmp.py ...` regardless
# of cwd (uv does not add the project root to sys.path automatically).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    from core.tools.xmp import read_namespaces

    rc = 0
    for arg in argv:
        p = Path(arg)
        print(f"=== {arg} ===")
        if not p.exists():
            print("  FILE NOT FOUND")
            rc = 1
            continue
        try:
            data = read_namespaces(str(p))
        except Exception as exc:  # noqa: BLE001
            print(f"  XMP read error: {type(exc).__name__}: {exc}")
            rc = 1
            continue
        sweep = data.get_attrs("sweep")
        wd = data.get_attrs("wdtag")
        if not sweep:
            print("  no sweep XMP (this image was not generated through Sweep mode,")
            print("  or was generated before v4.140.0 added the XMP write path)")
        else:
            print("  sweep attrs:")
            for k, v in sorted(sweep.items()):
                print(f"    {k} = {v}")
        if wd:
            print(f"  wdtag attrs: {len(wd)} keys present")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
