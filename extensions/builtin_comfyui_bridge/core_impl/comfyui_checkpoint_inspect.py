"""Inspect ComfyUI checkpoint files to detect model family (SDXL / SD1.5 / etc).

Reads only the safetensors JSON header (first 8 bytes give header size, then
header_size bytes of JSON) so the multi-GB weight payload is never touched.
"""

from __future__ import annotations

import json
import logging
import os
import struct
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Cap header read to a sane value -- real safetensors headers are typically
# <1 MB even for huge models. Anything larger is almost certainly garbage.
_MAX_HEADER_BYTES = 16 * 1024 * 1024

# Cache: {abs_path: (mtime_ns, size, family, metadata)}
# Bounded to prevent unbounded growth in long-running sessions that rotate
# through many checkpoints.  Oldest entries are evicted when the limit is hit.
_CACHE: dict[str, tuple[int, int, str, dict[str, Any]]] = {}
_CACHE_MAX_ENTRIES = 256


def _read_safetensors_header(path: Path) -> dict[str, Any] | None:
    """Return the parsed safetensors JSON header, or ``None`` on failure."""
    try:
        with path.open("rb") as f:
            size_bytes = f.read(8)
            if len(size_bytes) < 8:
                return None
            (header_size,) = struct.unpack("<Q", size_bytes)
            if header_size <= 0 or header_size > _MAX_HEADER_BYTES:
                logger.warning("safetensors header size out of range: %s (%s)", header_size, path)
                return None
            payload = f.read(header_size)
            if len(payload) < header_size:
                return None
            return json.loads(payload.decode("utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("failed to read safetensors header %s: %s", path, exc)
        return None


def _detect_family_from_header(header: dict[str, Any]) -> str:
    """Classify the checkpoint family from its safetensors header.

    Returns one of: "sd15", "sdxl", "flux", "sd3", "qwen3", "t5only", "unknown".
    """
    meta = header.get("__metadata__") or {}

    # 1. Metadata architecture hint.
    # Qwen3 / T5-only are checked first to prevent misclassification when a
    # checkpoint's metadata contains mixed arch strings (e.g. both "qwen" and "xl").
    arch = str(meta.get("modelspec.architecture", "")).lower()
    if "anima" in arch or "qwen" in arch:
        return "qwen3"
    if "pixart" in arch or "auraflow" in arch:
        return "t5only"
    if "xl" in arch or "sdxl" in arch:
        return "sdxl"
    if "flux" in arch:
        return "flux"
    if "sd3" in arch or "stable-diffusion-3" in arch:
        return "sd3"
    if "stable-diffusion-v1" in arch or "sd-v1" in arch or "sd_v1" in arch:
        return "sd15"

    keys = [k for k in header if k != "__metadata__"]
    if not keys:
        return "unknown"

    # 2. Qwen3 state_dict key pattern.
    # Prefixes verified via unit tests (test_comfyui_checkpoint_inspect.py).
    for k in keys:
        if k.startswith("model.text_encoders.qwen.") or k.startswith("text_encoders.qwen."):
            return "qwen3"

    # 3. SDXL: dual text encoder under conditioner.embedders.1.*, or class
    #    conditioning label_emb.* in the UNet. SD1.5 lacks both.
    for k in keys:
        if k.startswith("conditioner.embedders.1.") or k.startswith(
            "model.diffusion_model.label_emb."
        ):
            return "sdxl"

    # 4. Flux / SD3 use double_blocks / joint_blocks instead of input_blocks.
    for k in keys:
        if k.startswith("double_blocks.") or k.startswith("model.diffusion_model.double_blocks."):
            return "flux"
        if k.startswith("model.diffusion_model.joint_blocks."):
            return "sd3"

    # 5. Cross-attention dim. SDXL's attn2.to_k input dim is 2048 (vs 768 in SD1.5).
    for k in keys:
        if "attn2.to_k.weight" in k:
            shape = header[k].get("shape") if isinstance(header[k], dict) else None
            if isinstance(shape, list) and len(shape) >= 2:
                # Weight shape is [out, in]; in-dim is the context (text-encoder) dim.
                if shape[1] == 2048:
                    return "sdxl"
                if shape[1] == 768:
                    return "sd15"
            break

    # 6. Final fallback: classic SD1.5 has cond_stage_model.* keys.
    for k in keys:
        if k.startswith("cond_stage_model.transformer."):
            return "sd15"

    # 7. T5-only key pattern — placed after Flux/SD3 heuristics (steps 4 above)
    # to avoid misclassifying Flux (double_blocks) or SD3 (joint_blocks) as T5-only.
    # Prefixes verified via unit tests (test_comfyui_checkpoint_inspect.py).
    has_t5 = any(
        k.startswith(("model.text_encoders.t5.", "text_encoders.t5.")) for k in keys
    )
    has_clip = any(
        "cond_stage_model" in k or "clip_l" in k or "conditioner.embedders.0." in k
        for k in keys
    )
    has_flux_struct = any(
        k.startswith((
            "double_blocks.",
            "model.diffusion_model.double_blocks.",
            "joint_blocks.",
            "model.diffusion_model.joint_blocks.",
        ))
        for k in keys
    )
    if has_t5 and not has_clip and not has_flux_struct:
        return "t5only"

    return "unknown"


def _resolve_checkpoint_path(name: str, models_root: str) -> Path | None:
    """Resolve a checkpoint filename to an absolute path under ``models_root``.

    ``models_root`` may point at either ComfyUI's install dir, its ``models``
    dir, or the ``models/checkpoints`` dir directly. ``name`` may itself contain
    a subdirectory (e.g. ``SDXL/foo.safetensors``).
    """
    if not models_root or not name:
        return None
    root = Path(models_root).expanduser()
    if not root.is_absolute():
        return None

    # Reject path traversal.
    name_clean = name.replace("\\", "/").lstrip("/")
    if ".." in Path(name_clean).parts:
        return None

    candidates = [
        root / name_clean,
        root / "checkpoints" / name_clean,
        root / "models" / "checkpoints" / name_clean,
    ]
    try:
        root_resolved = root.resolve()
    except OSError:
        return None
    for cand in candidates:
        try:
            if not cand.is_file():
                continue
            resolved = cand.resolve()
        except OSError:
            continue
        # Final containment check after symlink resolution.
        try:
            resolved.relative_to(root_resolved)
        except ValueError:
            continue
        return resolved
    return None


def inspect_checkpoint(name: str, models_root: str) -> dict[str, Any]:
    """Return ``{family, source, path?, error?}`` for the named checkpoint.

    ``source`` is one of:
      - ``"header"``: family confirmed from safetensors header bytes.
      - ``"unavailable"``: file not locally accessible (remote ComfyUI, or
        ``models_root`` not configured / not found). Caller should fall back
        to filename heuristics and warn the user.
      - ``"unsupported"``: file found but not a safetensors file. Caller
        should fall back to filename heuristics.
    """
    if not name:
        return {"family": None, "source": "unavailable", "error": "name required"}

    if not models_root:
        return {"family": None, "source": "unavailable", "error": "models_root not configured"}

    path = _resolve_checkpoint_path(name, models_root)
    if path is None:
        return {"family": None, "source": "unavailable", "error": "file not found locally"}

    if path.suffix.lower() != ".safetensors":
        return {
            "family": None,
            "source": "unsupported",
            "path": str(path),
            "error": "only .safetensors files can be inspected",
        }

    try:
        st = path.stat()
    except OSError as exc:
        return {"family": None, "source": "unavailable", "error": str(exc)}

    cache_key = str(path)
    cached = _CACHE.get(cache_key)
    if cached is not None and cached[0] == st.st_mtime_ns and cached[1] == st.st_size:
        return {
            "family": cached[2],
            "source": "header",
            "path": cache_key,
            "metadata": cached[3],
            "cached": True,
        }

    header = _read_safetensors_header(path)
    if header is None:
        return {
            "family": None,
            "source": "unsupported",
            "path": cache_key,
            "error": "could not parse safetensors header",
        }

    family = _detect_family_from_header(header)
    meta = header.get("__metadata__") or {}
    # Strip large metadata values to keep response small.
    meta_small = {k: v for k, v in meta.items() if isinstance(v, str) and len(v) < 200}
    # Evict oldest entry when cap is reached (insertion-order dict, Python 3.7+).
    if len(_CACHE) >= _CACHE_MAX_ENTRIES:
        import contextlib
        with contextlib.suppress(StopIteration):
            _CACHE.pop(next(iter(_CACHE)))
    _CACHE[cache_key] = (st.st_mtime_ns, st.st_size, family, meta_small)

    return {
        "family": family,
        "source": "header",
        "path": cache_key,
        "metadata": meta_small,
        "cached": False,
    }


def auto_detect_models_root(api_url: str) -> str:
    """Best-effort guess at ComfyUI's models dir on the local machine.

    Only returns a value when the API URL points at the local host AND a
    well-known install path exists. Otherwise returns ``""`` and the caller
    should require explicit configuration.
    """
    if not api_url:
        return ""
    host = api_url.split("://", 1)[-1].split(":", 1)[0].split("/", 1)[0].lower()
    if host not in ("127.0.0.1", "localhost", "::1"):
        return ""

    candidates: list[Path] = []
    # Common Windows / portable layouts.
    if os.name == "nt":
        for drive in ("C:", "D:", "O:"):
            candidates.append(Path(f"{drive}/ComfyUI/models"))
            candidates.append(Path(f"{drive}/ComfyUI_windows_portable/ComfyUI/models"))
            candidates.append(Path(f"{drive}/comfyui/models"))
    candidates.append(Path.home() / "ComfyUI" / "models")
    candidates.append(Path.home() / "comfyui" / "models")

    for cand in candidates:
        try:
            if (cand / "checkpoints").is_dir():
                return str(cand)
        except OSError:
            continue
    return ""
