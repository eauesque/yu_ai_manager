"""Text encoder kind detection and dispatch for ComfyUI Bridge.

Provides architecture-agnostic detection of the text-encoder family used by a
checkpoint and maps it to a ComfyUI node recipe. This avoids BNK_CLIPTextEncodeAdvanced
being called with Qwen3-based checkpoints (Anima, Qwen-Image), which would raise
KeyError: 'l' because BNK hard-codes CLIP-L tokenizer assumptions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum

logger = logging.getLogger(__name__)

try:
    from .comfyui_checkpoint_inspect import inspect_checkpoint
except ImportError:  # pragma: no cover - direct import path (tests / top-level)
    from comfyui_checkpoint_inspect import inspect_checkpoint


class TextEncoderKind(StrEnum):
    """Text encoder architecture family.

    Inherits StrEnum (Python 3.11+) so json.dumps() serialises instances as
    plain strings without a custom encoder, making them safe to embed in
    emit() payloads.
    """
    CLIP_L      = "clip_l"        # SD 1.5
    CLIP_L_G    = "clip_l_g"      # SDXL / Illustrious / Pony
    CLIP_L_T5   = "clip_l_t5"     # Flux.1 dev / schnell
    CLIP_L_G_T5 = "clip_l_g_t5"  # SD3 / SD3.5
    QWEN3       = "qwen3"         # Anima / Qwen-Image series (IMAGE only)
    #
    # NOTE: Wan image (QWEN3) vs Wan video use DIFFERENT ComfyUI clip_types:
    #   image: CLIPLoader(type="qwen_image"), EmptyLatentImage (4ch), qwen_image_vae
    #   video: CLIPLoader(type="wan"),        video latent nodes,      wan_2.1_vae
    # If Wan video is ever supported, add QWEN3_VIDEO = "qwen3_video" as a SEPARATE kind.
    # Do NOT reuse QWEN3 for video — the node graph is fundamentally different.
    #
    T5_ONLY     = "t5_only"       # PixArt / AuraFlow
    UNKNOWN     = "unknown"       # Detection attempted but inconclusive (safe fallback)


@dataclass(frozen=True)
class NodeRecipe:
    """Immutable recipe describing which ComfyUI text-encode node to use."""

    class_type: str            # ComfyUI node class name
    supports_a1111_adv: bool   # Whether BNK_CLIPTextEncodeAdvanced may be substituted
    extra_inputs: dict = field(default_factory=dict)


# Maps each TextEncoderKind to its ComfyUI node recipe.
# All current recipes use CLIPTextEncode; QWEN3/T5_ONLY/UNKNOWN have
# supports_a1111_adv=False to prevent BNK substitution.
TEXT_ENCODER_NODE_MAP: dict[TextEncoderKind, NodeRecipe] = {
    TextEncoderKind.CLIP_L:      NodeRecipe("CLIPTextEncode", True),
    TextEncoderKind.CLIP_L_G:    NodeRecipe("CLIPTextEncode", True),
    TextEncoderKind.CLIP_L_T5:   NodeRecipe("CLIPTextEncode", True),
    TextEncoderKind.CLIP_L_G_T5: NodeRecipe("CLIPTextEncode", True),
    TextEncoderKind.QWEN3:       NodeRecipe("CLIPTextEncode", False),
    TextEncoderKind.T5_ONLY:     NodeRecipe("CLIPTextEncode", False),
    TextEncoderKind.UNKNOWN:     NodeRecipe("CLIPTextEncode", False),
}

# Maps safetensors-header family strings (from inspect_checkpoint) to TextEncoderKind.
# Intentionally omits "unknown" so that header-unknown checkpoints fall through
# to filename heuristics rather than immediately returning UNKNOWN.
#
# NOTE: "qwen3" and "t5only" are forward-compatibility placeholders.
# comfyui_checkpoint_inspect._detect_family_from_header() currently does NOT
# return these values; they become reachable only after Task 2 extends that
# function. The filename heuristic path serves as the interim fallback.
_FAMILY_TO_KIND: dict[str, TextEncoderKind] = {
    "sd15":   TextEncoderKind.CLIP_L,
    "sdxl":   TextEncoderKind.CLIP_L_G,
    "flux":   TextEncoderKind.CLIP_L_T5,
    "sd3":    TextEncoderKind.CLIP_L_G_T5,
    "qwen3":  TextEncoderKind.QWEN3,    # active after checkpoint_inspect Task 2
    "t5only": TextEncoderKind.T5_ONLY,  # active after checkpoint_inspect Task 2
    # "unknown" is intentionally absent — allows filename heuristic fallthrough
}


def te1_kind_hint(te1_name: str) -> TextEncoderKind | None:
    """Return TextEncoderKind from *text_encoder_1* filename in separate-load mode.

    Only returns a kind when the encoder is **clearly BNK-incompatible** (e.g. Qwen3).
    Returns ``None`` for standard CLIP-based encoders so that the caller can
    preserve legacy ``a1111_mode``-based behaviour.

    Use case: ``diffusion_model`` is set (UNETLoader + CLIPLoader + VAELoader),
    and we need to know whether BNK may be used without inspecting the safetensors
    header of the diffusion model file.
    """
    name = te1_name.lower()
    # Qwen3-based text encoders used by Anima / Qwen-Image.
    # "anima" boundaries ("anima-", "anima_", "anima.") prevent false-positive on
    # "animagine" which is an SDXL checkpoint with CLIP-L/G.
    if any(x in name for x in ("anima-", "anima_", "anima.", "qwen")):
        return TextEncoderKind.QWEN3
    # Standard CLIP-L, CLIP-G, DualCLIP, T5+CLIP combos — caller decides via a1111_mode.
    return None


def detect_text_encoder_kind(
    ckpt_name: str,
    models_root: str,
) -> tuple[TextEncoderKind, str]:
    """Return (TextEncoderKind, detection_source) for the named checkpoint.

    detection_source values:
      "header"   — family confirmed from safetensors header bytes
      "filename" — inferred from checkpoint filename heuristics
      "unknown"  — detection attempted but inconclusive

    Note: separate-load mode (diffusion_model set) is handled by the caller;
    in that case this function is NOT called and None is passed to the workflow
    builder instead to preserve legacy behavior.
    """
    result = inspect_checkpoint(ckpt_name, models_root)

    if result.get("source") == "header":
        family = result.get("family") or ""
        # "unknown" family intentionally falls through to filename heuristics
        if family and family != "unknown" and family in _FAMILY_TO_KIND:
            return _FAMILY_TO_KIND[family], "header"

    # Header "unknown" / unreadable / unmapped → filename heuristics.
    # "anima" is matched with a trailing separator to avoid false-positive on
    # "Animagine" (SDXL model whose name contains the "anima" substring).
    name_lower = ckpt_name.lower()
    if any(x in name_lower for x in ("anima-", "anima_", "anima.", "qwen")):
        return TextEncoderKind.QWEN3, "filename"
    if any(x in name_lower for x in ("auraflow", "pixart")):
        return TextEncoderKind.T5_ONLY, "filename"

    return TextEncoderKind.UNKNOWN, "unknown"


__all__ = [
    "TextEncoderKind",
    "NodeRecipe",
    "TEXT_ENCODER_NODE_MAP",
    "detect_text_encoder_kind",
    "te1_kind_hint",
]
