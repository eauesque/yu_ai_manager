"""Embed Sweep run metadata into generated image files via XMP.

A "Sweep" is one parameter-axis run from the image-generation bridges
(NAI / ComfyUI / SD WebUI). Every image in the same sweep shares an ``id``
and the axis definitions, but each image carries its own per-axis
``index`` / ``value`` so it can be located within the run.

The data is stored in the ``sweep`` XMP namespace (registered in
:mod:`core.tools.xmp.registry`). It coexists with WD-Tagger's ``wdtag``
attrs and ``dc:subject`` tag list because writes go through
:func:`core.tools.xmp.merge_into_file`, which only touches the named
namespace.

Schema written for a 1-axis sweep::

    sweep:id            = "uuid"
    sweep:bridge        = "nai" | "comfyui" | "sd-webui"
    sweep:axis_count    = "1"
    sweep:base_seed     = "1234567"
    sweep:created_at    = "1714992000"   (unix seconds)
    sweep:axis_0_param  = "cfg_rescale"
    sweep:axis_0_total  = "6"
    sweep:axis_0_series = "0,0.2,0.4,0.6,0.8,1.0"
    sweep:axis_0_index  = "2"
    sweep:axis_0_value  = "0.4"

2- and 3-axis sweeps add ``sweep:axis_{1,2}_*`` attrs in the same shape.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from core.tools.xmp import merge_into_file

logger = logging.getLogger(__name__)

_VALID_BRIDGES = {"nai", "comfyui", "sd-webui"}

# Pseudo-param marker for the Prompt macros (S/R) axis. Series + value entries
# are dicts (mapping slot index → substituted value), so they can't ride on the
# regular comma-joined storage; we JSON-encode them instead.
_MACROS_PARAM = "_macros"


def validate_sweep_meta(meta: Any) -> dict | None:
    """Return a normalized sweep_meta dict, or ``None`` if the input is invalid.

    Untrusted client input — we never raise, just drop the meta if anything
    looks wrong. The image generation succeeds either way; XMP is best-effort.
    """
    if not isinstance(meta, dict):
        return None
    sweep_id = meta.get("id")
    bridge = meta.get("bridge")
    axes = meta.get("axes")
    if not isinstance(sweep_id, str) or not sweep_id:
        return None
    if bridge not in _VALID_BRIDGES:
        return None
    if not isinstance(axes, list) or not (1 <= len(axes) <= 3):
        return None
    norm_axes: list[dict] = []
    for ax in axes:
        if not isinstance(ax, dict):
            return None
        param = ax.get("param")
        if not isinstance(param, str) or not param:
            return None
        try:
            index = int(ax.get("index", 0))
            total = int(ax.get("total", 0))
        except (TypeError, ValueError):
            return None
        if total <= 0 or index < 0 or index >= total:
            return None
        series = ax.get("series")
        if not isinstance(series, list):
            return None
        value = ax.get("value")
        norm_axes.append({
            "param": param,
            "index": index,
            "total": total,
            "value": value,
            "series": series,
        })

    try:
        base_seed = int(meta.get("base_seed", -1))
    except (TypeError, ValueError):
        base_seed = -1
    try:
        created_at = int(meta.get("created_at", 0))
    except (TypeError, ValueError):
        created_at = 0

    # Optional: original prompt/negative *before* macro/S-R substitution.
    # Re-run flows need the template (with `$x1` etc. intact) — without it,
    # the destination bridge bakes in the substituted values from the
    # last image's metadata.
    pt = meta.get("prompt_template")
    nt = meta.get("negative_template")
    prompt_template = pt if isinstance(pt, str) else None
    negative_template = nt if isinstance(nt, str) else None

    out: dict = {
        "id": sweep_id,
        "bridge": bridge,
        "axes": norm_axes,
        "base_seed": base_seed,
        "created_at": created_at,
    }
    if prompt_template is not None:
        out["prompt_template"] = prompt_template
    if negative_template is not None:
        out["negative_template"] = negative_template
    # Optional run-level fields used by the /sweep history filter (DB
    # backed). All best-effort: bridges that don't expose a field just
    # skip it, and the matching filter checkbox shows as disabled.
    for key in ("checkpoint", "vae", "sampler"):
        v = meta.get(key)
        if isinstance(v, str) and v:
            out[key] = v
    for key in ("width", "height", "steps"):
        v = meta.get(key)
        try:
            iv = int(v) if v is not None else None
        except (TypeError, ValueError):
            iv = None
        if iv is not None and iv > 0:
            out[key] = iv
    cfg_v = meta.get("cfg")
    try:
        cfg_f = float(cfg_v) if cfg_v is not None else None
    except (TypeError, ValueError):
        cfg_f = None
    if cfg_f is not None:
        out["cfg"] = cfg_f
    return out


def _series_to_str(series: list) -> str:
    parts: list[str] = []
    for v in series:
        if isinstance(v, float):
            # Trim trailing zeros for compactness, keep enough precision.
            parts.append(f"{v:g}")
        else:
            parts.append(str(v))
    return ",".join(parts)


def sweep_meta_to_attrs(meta: dict) -> dict[str, str]:
    """Flatten a normalized sweep_meta into ``sweep:*`` attribute strings."""
    attrs: dict[str, str] = {
        "id": meta["id"],
        "bridge": meta["bridge"],
        "axis_count": str(len(meta["axes"])),
        "base_seed": str(meta["base_seed"]),
        "created_at": str(meta["created_at"]),
    }
    if "prompt_template" in meta:
        attrs["prompt_template"] = meta["prompt_template"]
    if "negative_template" in meta:
        attrs["negative_template"] = meta["negative_template"]
    # Run-level filter fields (best-effort).
    for key in ("checkpoint", "vae", "sampler"):
        if key in meta:
            attrs[key] = str(meta[key])
    for key in ("width", "height", "steps"):
        if key in meta:
            attrs[key] = str(meta[key])
    if "cfg" in meta:
        cfg = meta["cfg"]
        attrs["cfg"] = f"{cfg:g}" if isinstance(cfg, float) else str(cfg)
    for i, ax in enumerate(meta["axes"]):
        prefix = f"axis_{i}_"
        attrs[prefix + "param"] = ax["param"]
        attrs[prefix + "total"] = str(ax["total"])
        attrs[prefix + "index"] = str(ax["index"])
        if ax["param"] == _MACROS_PARAM:
            # Series + value are dicts (slot_idx -> substituted value).
            # Comma-joining would collide with JSON commas, so encode the
            # whole structure as a single JSON string per attr.
            attrs[prefix + "series"] = json.dumps(ax["series"], ensure_ascii=False)
            if ax["value"] is not None:
                attrs[prefix + "value"] = json.dumps(ax["value"], ensure_ascii=False)
        else:
            attrs[prefix + "series"] = _series_to_str(ax["series"])
            if ax["value"] is not None:
                v = ax["value"]
                attrs[prefix + "value"] = f"{v:g}" if isinstance(v, float) else str(v)
    return attrs


def write_sweep_xmp(image_path: str, meta: dict | Any) -> bool:
    """Write sweep metadata into one image. Returns False on validation failure."""
    norm = validate_sweep_meta(meta)
    if not norm:
        logger.debug("write_sweep_xmp: invalid meta, skipping (path=%s)", image_path)
        return False
    attrs = sweep_meta_to_attrs(norm)
    try:
        return merge_into_file(image_path, prefix="sweep", attrs=attrs, replace_attrs=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("write_sweep_xmp failed for %s: %s", image_path, exc)
        return False


def write_sweep_xmp_to_paths(paths: list[str], meta: dict | Any) -> int:
    """Write sweep XMP to each path. Returns count of successful writes."""
    if not paths:
        return 0
    norm = validate_sweep_meta(meta)
    if not norm:
        return 0
    attrs = sweep_meta_to_attrs(norm)
    ok = 0
    for p in paths:
        try:
            if merge_into_file(p, prefix="sweep", attrs=attrs, replace_attrs=True):
                ok += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("write_sweep_xmp failed for %s: %s", p, exc)
    return ok


__all__ = [
    "sweep_meta_to_attrs",
    "validate_sweep_meta",
    "write_sweep_xmp",
    "write_sweep_xmp_to_paths",
]
