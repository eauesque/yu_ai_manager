"""Server-side Dynamic Prompt / Wildcard expansion for Bridge."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _load_wildcards() -> dict:
    """Load wildcard dictionaries from Prompt Simulator config."""
    try:
        from importlib import import_module

        from core.extensions_core.extensions_admin import get_extension_config_value
        wc_mod = import_module(
            "extensions.builtin_prompt_simulator.core_impl.wildcard_loader"
        )

        dirs = get_extension_config_value(
            "builtin-prompt-simulator", "wildcard_dirs", [])
        if not dirs:
            return {}
        wc, _sources = wc_mod.load_wildcards_from_dirs(dirs)
        return wc
    except Exception:
        return {}


def maybe_expand_prompt(
    prompt: str, negative: str, expand: bool, seed: int | None = None,
    extra_wildcards: dict | None = None,
) -> dict[str, Any]:
    """If *expand* is True, run DP/WC expansion on prompt & negative.

    *extra_wildcards* are merged on top of filesystem wildcards (e.g. from
    the client-side Wildcard Manager).

    Returns ``{prompt, negative, expanded, original_prompt, original_negative}``.
    """
    if not expand:
        return {"prompt": prompt, "negative": negative, "expanded": False}

    from core.prompt.convert import expand_dynamic_prompt

    wc = _load_wildcards()
    if extra_wildcards:
        wc.update(extra_wildcards)
    new_p = expand_dynamic_prompt(prompt, seed=seed, wildcards=wc)
    new_n = expand_dynamic_prompt(negative, seed=seed, wildcards=wc)
    changed = (new_p != prompt) or (new_n != negative)
    return {
        "prompt": new_p,
        "negative": new_n,
        "expanded": changed,
        "original_prompt": prompt if changed else None,
        "original_negative": negative if changed else None,
    }


def expand_text(
    text: str, seed: int | None = None,
    extra_wildcards: dict | None = None,
) -> str:
    """Expand a single text string (e.g. NAI character prompt)."""
    from core.prompt.convert import expand_dynamic_prompt

    wc = _load_wildcards()
    if extra_wildcards:
        wc.update(extra_wildcards)
    return expand_dynamic_prompt(text, seed=seed, wildcards=wc)
