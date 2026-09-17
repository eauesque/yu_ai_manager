"""NAI Undesired Content presets and Quality Tags.

NovelAI's own web UI expands both of these **client side** before sending:
the UC preset text is prepended to the undesired content ("Added to the
beginning of the UC") and the quality tags are appended to the prompt
("Added to the end of the prompt"). ``/ai/generate-image`` receives the
already-expanded strings; the ``ucPreset`` integer and ``qualityToggle``
boolean that travel alongside them are metadata, not instructions — so a
client that only sends those applies neither.

This module therefore holds the text and the bridge does the same
expansion NovelAI does. ``ucPreset`` is then reported as :data:`UC_NONE`
and ``qualityToggle`` as ``False``, so neither can be applied twice
whichever way the server treats them.

Mirror: `crates/yu-server/src/routes/nai_bridge.rs`.
`tests/test_nai_uc_presets.py` fails if the two sides drift apart.

The text differs between model generations, so every table is keyed by
generation and a generation with no recorded text is left untouched
rather than fed another generation's words.
"""

from __future__ import annotations

# Selector values. 0-2 predate this module and are kept as-is so saved
# parameters and LAN peers keep their meaning; 3-4 are new.
UC_HEAVY = 0
UC_LIGHT = 1
UC_NONE = 2
UC_HUMAN_FOCUS = 3
UC_FURRY_FOCUS = 4

GEN_V5 = "v5"
GEN_V45 = "v45"
GEN_V4 = "v4"

# NovelAI Diffusion V5 undesired-content presets, verbatim from the V5 UI.
_UC_V5: dict[int, str] = {
    UC_HEAVY: (
        "lowres, artistic error, film grain, scan artifacts, worst quality, "
        "bad quality, jpeg artifacts, very displeasing, chromatic aberration, "
        "dithering, halftone, screentone, multiple views, logo, "
        "too many watermarks, negative space, blank page"
    ),
    UC_LIGHT: (
        "lowres, bad hands, bad anatomy, artistic error, sepia, white haze, "
        "worst quality, very displeasing, jpeg artifacts, 0::ai-generated::"
    ),
    UC_NONE: "",
    UC_HUMAN_FOCUS: (
        "lowres, artistic error, film grain, scan artifacts, worst quality, "
        "bad quality, jpeg artifacts, very displeasing, chromatic aberration, "
        "dithering, halftone, screentone, multiple views, logo, "
        "too many watermarks, negative space, blank page, @_@, "
        "mismatched pupils, glowing eyes, bad anatomy"
    ),
    UC_FURRY_FOCUS: (
        "{worst quality}, distracting watermark, unfinished, bad quality, "
        "{widescreen}, upscale, {sequence}, {{grandfathered content}}, "
        "blurred foreground, chromatic aberration, sketch, everyone, "
        "[sketch background], simple, [flat colors], ych (character), "
        "outline, multiple scenes, [[horror (theme)]], comic"
    ),
}

# NovelAI Diffusion V4.5 undesired-content presets, verbatim from the V4.5
# UI. Furry Focus is absent because V4.5's UC preset list no longer offers it
# — not for want of capturing it. The Anime/Furry switch does not change
# these texts: both modes show the same wording (checked against the live
# V5 UI), so one table per generation is the whole story.
_UC_V45: dict[int, str] = {
    UC_HEAVY: (
        "blurry, lowres, upscaled, artistic error, film grain, scan artifacts, "
        "worst quality, bad quality, jpeg artifacts, very displeasing, "
        "chromatic aberration, halftone, multiple views, logo, "
        "too many watermarks, negative space, blank page"
    ),
    UC_LIGHT: (
        "blurry, lowres, upscaled, artistic error, scan artifacts, "
        "jpeg artifacts, logo, too many watermarks, negative space, blank page"
    ),
    UC_NONE: "",
    UC_HUMAN_FOCUS: (
        "blurry, lowres, upscaled, artistic error, film grain, scan artifacts, "
        "bad anatomy, bad hands, worst quality, bad quality, jpeg artifacts, "
        "very displeasing, chromatic aberration, halftone, multiple views, "
        "logo, too many watermarks, @_@, mismatched pupils, glowing eyes, "
        "negative space, blank page"
    ),
}

# NovelAI Diffusion V4 undesired-content presets, verbatim from the V4 UI.
# V4 offers Heavy / Light / None only — no focus presets.
_UC_V4: dict[int, str] = {
    UC_HEAVY: (
        "blurry, lowres, error, film grain, scan artifacts, worst quality, "
        "bad quality, jpeg artifacts, very displeasing, chromatic aberration, "
        "logo, dated, signature, multiple views, gigantic breasts, "
        "white blank page, blank page"
    ),
    UC_LIGHT: (
        "blurry, lowres, error, worst quality, bad quality, jpeg artifacts, "
        "very displeasing, logo, dated, signature, white blank page, blank page"
    ),
    UC_NONE: "",
}

UC_PRESETS: dict[str, dict[int, str]] = {
    GEN_V5: _UC_V5,
    GEN_V45: _UC_V45,
    GEN_V4: _UC_V4,
}

# Quality Tags ("Standard"), appended to the end of the prompt.
QUALITY_TAGS: dict[str, str] = {
    GEN_V5: "very aesthetic, masterpiece, no text",
    GEN_V45: "very aesthetic, masterpiece, no text, -0.8::feet::, rating:general",
    GEN_V4: "rating:general, best quality, very aesthetic, absurdres",
}

# Backwards-compatible alias for the V5 table.
UC_PRESETS_V5 = _UC_V5

# Dataset mode. NovelAI folded the Furry model into the base model; the UI's
# Anime/Furry switch (the cherry-blossom / paw icon next to the base prompt)
# has no API flag of its own — Furry mode simply puts the ``fur dataset`` tag
# at the very start of the base prompt.
MODE_ANIME = "anime"
MODE_FURRY = "furry"

MODE_PREFIXES: dict[str, str] = {
    MODE_ANIME: "",
    MODE_FURRY: "fur dataset",
}


def expand_mode_prefix(mode: str, prompt: str) -> str:
    """Return ``prompt`` with the dataset-mode tag at the very start.

    NovelAI documents that the tag only works from the start of the base
    prompt. An unknown mode is treated as Anime (no prefix) rather than
    guessed at.
    """
    prefix = MODE_PREFIXES.get(mode, "")
    if not prefix:
        return prompt
    existing = prompt.strip()
    return f"{prefix}, {existing}" if existing else prefix


def model_generation(model: str) -> str | None:
    """Return the generation key for ``model``, or ``None`` if unrecorded.

    The V4 text was captured from one V4 model and is applied to both
    ``nai-diffusion-4-full`` and ``nai-diffusion-4-curated-preview``.
    """
    if model.startswith("nai-diffusion-5"):
        return GEN_V5
    if model.startswith("nai-diffusion-4-5"):
        return GEN_V45
    if model.startswith("nai-diffusion-4"):
        return GEN_V4
    return None


def expand_uc_preset(model: str, uc_preset: int, negative_prompt: str) -> tuple[str, int]:
    """Return ``(negative_prompt, uc_preset)`` with the preset prepended.

    The preset text for ``model``'s generation is prepended exactly as the
    NovelAI UI does, and the reported preset becomes :data:`UC_NONE` so the
    server cannot apply it a second time.

    A model whose generation has no recorded text is left alone, except
    that selector values that generation does not offer are reported as
    :data:`UC_NONE` rather than forwarded — an unverified integer would ask
    the server for some undesired preset, not for none.
    """
    table = UC_PRESETS.get(model_generation(model) or "")
    if table is None:
        if uc_preset in (UC_HUMAN_FOCUS, UC_FURRY_FOCUS):
            return negative_prompt, UC_NONE
        return negative_prompt, uc_preset

    text = table.get(uc_preset)
    if not text:
        # Unknown-for-this-generation or explicitly None: apply nothing.
        return negative_prompt, UC_NONE

    existing = negative_prompt.strip()
    merged = f"{text}, {existing}" if existing else text
    return merged, UC_NONE


def expand_quality_tags(model: str, quality_toggle: bool, prompt: str) -> tuple[str, bool]:
    """Return ``(prompt, quality_toggle)`` with the quality tags appended.

    Mirrors the NovelAI UI, which appends them to the end of the prompt.
    The reported toggle becomes ``False`` once the tags are in the prompt
    so they cannot be applied twice. A model generation with no recorded
    tags is left untouched.
    """
    if not quality_toggle:
        return prompt, False

    tags = QUALITY_TAGS.get(model_generation(model) or "")
    if not tags:
        return prompt, quality_toggle

    existing = prompt.strip()
    merged = f"{existing}, {tags}" if existing else tags
    return merged, False
