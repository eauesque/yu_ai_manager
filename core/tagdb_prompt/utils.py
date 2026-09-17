import os
import re
from pathlib import Path


def norm_space(s: str) -> str:
    s = (s or "").strip()
    return re.sub(r"\s+", " ", s)


def split_namespace(tag: str) -> tuple[str | None, str]:
    if ":" in tag:
        ns, rest = tag.split(":", 1)
        ns = norm_space(ns)
        rest = norm_space(rest)
        if ns and rest:
            return ns, rest
    normed = norm_space(tag)
    if normed.startswith("@"):
        rest = norm_space(normed[1:])
        if rest and re.search(r"[^\W_]", rest):
            return "artist", rest
    return None, normed


def normalize_path(p: Path) -> str:
    s = os.path.abspath(str(p))
    s = os.path.normpath(s)
    if os.name == "nt":
        s = os.path.normcase(s)
    return s
