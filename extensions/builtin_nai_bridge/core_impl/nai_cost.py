"""NAI Anlas cost estimation — isolated for easy formula updates.

Mirror: JS side is in nai_bridge_parts/_script.html (nabEstimateCost).
Update both files when NAI changes the pricing formula.
"""

from __future__ import annotations

import math

# -- Resolution presets (NAI official) ---------------------------------

RESOLUTION_PRESETS: list[tuple[str, int, int, str]] = [
    # (label, width, height, category)
    ("Normal Portrait", 832, 1216, "Normal"),
    ("Normal Landscape", 1216, 832, "Normal"),
    ("Normal Square", 1024, 1024, "Normal"),
    ("Large Portrait", 1024, 1536, "Large"),
    ("Large Landscape", 1536, 1024, "Large"),
    ("Large Square", 1472, 1472, "Large"),
    ("Wallpaper Portrait", 1088, 1920, "Wallpaper"),
    ("Wallpaper Landscape", 1920, 1088, "Wallpaper"),
    ("Small Portrait", 512, 768, "Small"),
    ("Small Landscape", 768, 512, "Small"),
    ("Small Square", 640, 640, "Small"),
]

# -- Max n_samples per resolution --------------------------------------


def max_samples(width: int, height: int) -> int:
    """Return the maximum number of samples allowed for a given resolution."""
    pixels = width * height
    if pixels <= 409_600:
        return 6
    if pixels <= 1_310_720:
        return 4
    if pixels <= 1_572_864:
        return 2
    return 1


# -- Cost formula constants (update here when NAI changes) -------------

_COEFF_BASE = 2.951823174884865e-6
_COEFF_STEP = 5.753298233447344e-7
_NORMAL_PORTRAIT_PX = 832 * 1216   # 1,011,712
_NORMAL_SQUARE_PX = 1024 * 1024    # 1,048,576


_ENCODE_VIBE_ANLAS = 2  # cost per /ai/encode-vibe call (Vibe Transfer + Precise Reference)


def is_opus_free_generation(width: int, height: int, steps: int) -> bool:
    """Whether a generation at this resolution/steps falls in the Opus free tier.

    Mirrors NovelAI's Opus Usage Limit eligibility rule: normal resolution
    (<= Normal Square pixel count) and steps <= 28. Independent of model --
    callers must additionally check the model is V5, since the Usage Limit
    (and its free tier) is a V5-only mechanism.
    """
    return steps <= 28 and (width * height) <= _NORMAL_SQUARE_PX


def estimate_anlas(
    width: int,
    height: int,
    steps: int,
    n_samples: int = 1,
    *,
    is_opus: bool = True,
    reference_count: int = 0,
) -> int:
    """Estimate the Anlas cost for a generation request.

    ``reference_count`` is the total number of reference images that will be
    encoded via ``/ai/encode-vibe`` (Vibe Transfer + Precise Reference entries).
    Each encode-vibe call costs :data:`_ENCODE_VIBE_ANLAS` (2 Anlas) regardless
    of the Opus free tier.

    Returns 0 when both generation and encoding are free.
    """
    r = max(width * height, 65_536)
    # Normal Square → adjust to Portrait price
    if _NORMAL_PORTRAIT_PX < r <= _NORMAL_SQUARE_PX:
        r = _NORMAL_PORTRAIT_PX
    per_image = max(math.ceil(_COEFF_BASE * r + _COEFF_STEP * r * steps), 2)
    opus_free = is_opus and is_opus_free_generation(width, height, steps)
    effective = n_samples - (1 if opus_free else 0)
    gen_cost = per_image * effective
    encode_cost = reference_count * _ENCODE_VIBE_ANLAS
    return gen_cost + encode_cost
