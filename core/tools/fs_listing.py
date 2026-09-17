"""Directory listing helpers for tools APIs."""

import socket
from pathlib import Path

from core.platform import list_roots


def safe_name(p: Path) -> str:
    try:
        return p.name or str(p)
    except Exception:
        return str(p)


def list_dirs_payload(raw_path: str) -> tuple[dict, int]:
    """Return directory listing response."""
    raw_path = (raw_path or "").strip()

    try:
        if raw_path:
            # Reject ~ to prevent home directory enumeration
            if "~" in raw_path:
                return {"error": "Paths containing '~' are not allowed"}, 400
            cur = Path(raw_path)
            if not cur.exists():
                return {"error": f"Path not found: {raw_path}"}, 404
            if not cur.is_dir():
                return {"error": f"Not a directory: {raw_path}"}, 400
            cur = cur.resolve()

            items = []
            for child in sorted(cur.iterdir(), key=lambda p: p.name.lower()):
                if child.is_dir():
                    items.append({"name": safe_name(child), "path": str(child)})

            parent = str(cur.parent) if cur.parent != cur else None
            return {
                "current": str(cur),
                "parent": parent,
                "roots": list_roots(),
                "dirs": items,
                "hostname": socket.gethostname(),
            }, 200

        roots = list_roots()
        return {
            "current": "",
            "parent": None,
            "roots": roots,
            "dirs": [{"name": r, "path": r} for r in roots],
            "hostname": socket.gethostname(),
        }, 200
    except PermissionError:
        return {"error": "Permission denied"}, 403
    except Exception:
        return {"error": "Directory listing failed"}, 500
