from __future__ import annotations

import re
from urllib.parse import unquote

from core.gateway.scopes import Scope

COMFY_ALLOWED_ENDPOINTS_EXACT: dict[tuple[str, str], Scope] = {
    ("POST", "/prompt"):       Scope.COMFY_GENERATE,
    ("GET",  "/queue"):        Scope.COMFY_QUERY,
    ("GET",  "/history"):      Scope.COMFY_QUERY,
    ("GET",  "/system_stats"): Scope.COMFY_QUERY,
    ("GET",  "/object_info"):  Scope.COMFY_QUERY,
    ("GET",  "/view"):         Scope.COMFY_QUERY,
    ("POST", "/upload/image"): Scope.COMFY_GENERATE,
    ("POST", "/upload/mask"):  Scope.COMFY_GENERATE,
}
COMFY_ALLOWED_ENDPOINTS_PREFIX: dict[tuple[str, str], Scope] = {
    ("GET", "/history/"):    Scope.COMFY_QUERY,
    ("GET", "/object_info/"): Scope.COMFY_QUERY,
}

_PREFIX_SEG = re.compile(r"^[0-9a-zA-Z_\-]{1,128}$")
_ALLOWED_TYPES = {"output", "input", "temp"}
_CTRL = re.compile(r"[\x00-\x1f\x7f]")
_WIN_SPECIAL = re.compile(r'[><|*?":]+')
_DRIVE = re.compile(r"^[a-zA-Z]:[/\\]")
_BEARER_PREFIX = "bearer."
_CLIENT_ID_RE = re.compile(r"^[0-9a-zA-Z_\-]{1,64}$")


def get_comfy_scope(method: str, path: str) -> Scope | None:
    key = (method.upper(), path)
    if key in COMFY_ALLOWED_ENDPOINTS_EXACT:
        return COMFY_ALLOWED_ENDPOINTS_EXACT[key]
    for (m, prefix), scope in COMFY_ALLOWED_ENDPOINTS_PREFIX.items():
        if method.upper() == m and path.startswith(prefix):
            seg = path[len(prefix):]
            if _PREFIX_SEG.match(seg):
                return scope
    return None


def validate_view_params(filename: str, subfolder: str, type_: str) -> str | None:
    """Return error string if invalid, None if OK."""
    try:
        fn = unquote(filename, errors="strict")
        sf = unquote(subfolder, errors="strict")
    except UnicodeDecodeError:
        return "invalid encoding"
    if "%" in fn or "%" in sf:
        return "double-encoding"
    if "\x00" in fn or "\x00" in sf:
        return "nul byte"
    if type_ not in _ALLOWED_TYPES:
        return f"invalid type {type_!r}"
    if "/" in fn or "\\" in fn:
        return "path separator in filename"
    if ".." in fn:
        return "dotdot"
    if fn.startswith("/") or fn.startswith("\\") or _DRIVE.match(fn):
        return "absolute path"
    if _CTRL.search(fn):
        return "control char"
    fn_bytes = fn.encode("utf-8")
    if len(fn_bytes) == 0 or len(fn_bytes) > 255:
        return "length out of range"
    if sf:
        segs = re.split(r"[/\\]", sf)
        if len(segs) > 8:
            return "too many segments"
        for seg in segs:
            if seg in ("", ".", "..") or _DRIVE.match(seg + "/") or _CTRL.search(seg) or _WIN_SPECIAL.search(seg):
                return f"invalid segment {seg!r}"
    return None


def extract_bearer_from_subprotocols(subprotocols: list[str]) -> tuple[str | None, list[str]]:
    token = None
    remaining = []
    for sp in subprotocols:
        if sp.startswith(_BEARER_PREFIX):
            token = sp[len(_BEARER_PREFIX):]
        else:
            remaining.append(sp)
    return token, remaining


def validate_client_id(client_id: str) -> bool:
    return bool(_CLIENT_ID_RE.match(client_id))
