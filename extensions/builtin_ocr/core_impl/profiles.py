"""3b: Community profiles -- external retrieval and management of model capability scores.

Retrieves model profiles from local JSON files or remote URLs
and extends OcrRouter capability templates.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Local profile save location
_PROFILES_DIR = Path(__file__).resolve().parent.parent / "profiles"
_LOCAL_PROFILES_FILE = _PROFILES_DIR / "model_profiles.json"
_CACHE_DURATION = 86400  # 24 hours
_cached_profiles: dict[str, dict[str, int]] | None = None
_cached_at: float = 0.0


def get_profiles_dir() -> Path:
    """Return the profile directory (create if absent)."""
    _PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    return _PROFILES_DIR


def load_profiles(
    force_refresh: bool = False,
) -> dict[str, dict[str, int]]:
    """Load model profiles.

    Returns:
        { "model_prefix": { "task": score, ... }, ... }
    """
    global _cached_profiles, _cached_at

    if not force_refresh and _cached_profiles is not None and time.monotonic() - _cached_at < _CACHE_DURATION:
        return _cached_profiles

    profiles: dict[str, dict[str, int]] = {}

    # 1. Built-in defaults (_DEFAULT_CAPABILITIES in router.py)
    from .router import _DEFAULT_CAPABILITIES
    profiles.update(_DEFAULT_CAPABILITIES)

    # 2. Override with local profiles
    local = _load_local_profiles()
    profiles.update(local)

    _cached_profiles = profiles
    _cached_at = time.monotonic()
    return profiles


def _load_local_profiles() -> dict[str, dict[str, int]]:
    """Load profiles from a local JSON file."""
    if not _LOCAL_PROFILES_FILE.exists():
        return {}
    try:
        data = json.loads(_LOCAL_PROFILES_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "profiles" in data:
            profiles = data["profiles"]
            return profiles if isinstance(profiles, dict) else {}
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("Failed to load local profiles: %s", exc)
        return {}


def save_local_profiles(profiles: dict[str, dict[str, int]]) -> None:
    """Save local profiles."""
    get_profiles_dir()
    data = {
        "version": 1,
        "updated_at": int(time.time()),
        "profiles": profiles,
    }
    _LOCAL_PROFILES_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    # Invalidate cache
    global _cached_profiles
    _cached_profiles = None
    logger.info("Saved %d model profiles to %s", len(profiles), _LOCAL_PROFILES_FILE)


def fetch_community_profiles(
    url: str,
    timeout: int = 15,
) -> dict[str, Any]:
    """Fetch community profiles from a remote URL.

    Returns:
        { "profiles": {...}, "source": url, "fetched_at": timestamp }
    """
    import urllib.request

    from core.analysis.openai_compat_utils import validate_openai_compat_url

    err = validate_openai_compat_url(url)
    if err:
        raise RuntimeError(err)

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "YU-AI-Manager", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except Exception as exc:
        logger.error("Failed to fetch community profiles from %s: %s", url, exc)
        raise RuntimeError(f"Failed to fetch profiles: {exc}") from exc

    # Validation
    if isinstance(data, dict) and "profiles" in data:
        profiles = data["profiles"]
    elif isinstance(data, dict):
        profiles = data
    else:
        raise RuntimeError("Invalid profile format: expected JSON object")

    # Score value validation
    validated: dict[str, dict[str, int]] = {}
    for model, scores in profiles.items():
        if not isinstance(scores, dict):
            continue
        validated[model] = {
            k: max(0, min(100, int(v)))
            for k, v in scores.items()
            if isinstance(v, (int, float))
        }

    return {
        "profiles": validated,
        "source": url,
        "fetched_at": int(time.time()),
        "model_count": len(validated),
    }


def merge_community_profiles(
    url: str,
    save: bool = True,
    timeout: int = 15,
) -> dict[str, Any]:
    """Fetch community profiles and merge locally.

    既存のローカルプロファイルと統合し、上書き保存する。
    """
    result = fetch_community_profiles(url, timeout)
    fetched = result["profiles"]

    # Merge with existing local profiles
    existing = _load_local_profiles()
    merged = {**existing, **fetched}

    if save:
        save_local_profiles(merged)

    result["merged_count"] = len(merged)
    result["new_models"] = len(set(fetched) - set(existing))
    result["updated_models"] = len(set(fetched) & set(existing))
    return result


def get_model_profile(model_tag: str) -> dict[str, int] | None:
    """Get a profile for a specific model. Partial match search."""
    profiles = load_profiles()
    tag_lower = model_tag.lower()
    for prefix, scores in profiles.items():
        if prefix.lower() in tag_lower:
            return scores
    return None


def update_model_profile(
    model_prefix: str, scores: dict[str, int],
) -> None:
    """Update a single model profile."""
    existing = _load_local_profiles()
    existing[model_prefix] = {
        k: max(0, min(100, int(v)))
        for k, v in scores.items()
        if isinstance(v, (int, float))
    }
    save_local_profiles(existing)


def list_profiles() -> list[dict[str, Any]]:
    """Return all profiles as a list."""
    profiles = load_profiles()
    result = []
    for model, scores in sorted(profiles.items()):
        result.append({
            "model": model,
            "scores": scores,
            "source": "local" if model in _load_local_profiles() else "builtin",
        })
    return result
