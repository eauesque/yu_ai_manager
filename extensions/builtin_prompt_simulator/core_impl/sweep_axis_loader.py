"""Load sweep axis value files for Bridge Prompt S/R.

Sweep axes share the on-disk format with prompt-simulator wildcards
(``.txt`` one-line-per-value, ``#`` comments, blank lines ignored) but
live in a *separate* directory tree so users can keep prompt wildcards
and sweep axis lists semantically apart. Optionally the regular wildcard
directories can also be searched as a secondary source.
"""

from __future__ import annotations

from .wildcard_parser import load_wildcards_from_dirs


def load_sweep_axes(
    axis_dirs: list[str],
    include_wildcard_dirs: bool = False,
    wildcard_dirs: list[str] | None = None,
) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Return ``(axes, sources)`` where ``sources[name]`` is ``"axis"`` or ``"wildcard"``.

    Resolution order: ``axis_dirs`` first, then (optionally) ``wildcard_dirs``.
    Names already provided by ``axis_dirs`` win — wildcard entries that share
    a name are dropped so the axis tree remains the authoritative source.
    """
    axes, _ = load_wildcards_from_dirs(axis_dirs or [])
    sources: dict[str, str] = {name: "axis" for name in axes}

    if include_wildcard_dirs and wildcard_dirs:
        wc_axes, _ = load_wildcards_from_dirs(wildcard_dirs)
        for name, lines in wc_axes.items():
            if name in axes:
                continue
            axes[name] = lines
            sources[name] = "wildcard"

    return axes, sources
