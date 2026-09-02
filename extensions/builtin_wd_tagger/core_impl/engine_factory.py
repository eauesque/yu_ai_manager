"""Engine factory for WD-Tagger (Phase 1b rewrite).

Internal: dispatches to the new TaggerAdapter framework for engine_type
"onnx" and "vlm". For engine_type "both" (composite) the legacy
CompositeWdTaggerEngine path is preserved — Phase 3 migrates this to
composite_profiles[].

External API is unchanged: ``get_engine(config) -> object`` (typed as
WdTaggerEngine for legacy callers; the new TaggerAdapter is quack-
compatible because it has tag_image / tag_images_batch / get_name /
is_available).

Caching: a module-level EngineCache (default size 1) is used for the
new framework paths. ``engine_type=both`` bypasses the cache because
its construction is cheap (delegates to two legacy engines whose own
state is sticky). Override the cache size via
``config.wd_tagger.engine_cache_size`` (default 1).

Thread-safety: the EngineCache itself is thread-safe. The module-level
``_engine_cache`` reference is lazily (re)built on first ``get_engine``
call after a config change in ``engine_cache_size`` — this lazy rebuild
is not synchronized, so callers are expected to not race ``get_engine``
with a config update. In practice, config updates clear the cache via
``clear_engine_cache()``.
"""
from __future__ import annotations

import logging
from typing import Any, cast

from .engine_cache import EngineCache
from .registry import TaggerRegistry

logger = logging.getLogger(__name__)


# Module-level cache. Sized via config.wd_tagger.engine_cache_size (default 1).
# Re-built on first get_engine() call so config changes take effect.
_engine_cache: EngineCache | None = None
_engine_cache_max_size: int = 0


def _get_or_build_cache(max_size: int) -> EngineCache:
    global _engine_cache, _engine_cache_max_size
    if _engine_cache is None or _engine_cache_max_size != max_size:
        _engine_cache = EngineCache(max_size=max_size)
        _engine_cache_max_size = max_size
        logger.info("EngineCache rebuilt with max_size=%d", max_size)
    return _engine_cache


def clear_engine_cache() -> None:
    """Drop all cached adapter instances.

    Preserved for backward compat with Phase 1a's clear_engine_cache().
    Callers (e.g. config_ops.save_config) invoke this when wd_tagger
    config keys change so the next get_engine() rebuilds the adapter.
    """
    global _engine_cache
    if _engine_cache is not None:
        _engine_cache.clear()
    _engine_cache = None


def _thresholds_from_config(config: dict[str, Any]) -> dict[str, float]:
    return {
        "general": float(config.get("general_threshold", 0.35)),
        "character": float(config.get("character_threshold", 0.85)),
        "rating": 0.0,
    }


def _thresholds_hash(thresholds: dict[str, float]) -> tuple:
    """Stable, hashable summary of threshold values for cache keys."""
    return tuple(sorted(thresholds.items()))


def _build_onnx_adapter_via_framework(config: dict[str, Any]) -> Any:
    """Build an ONNX adapter through the new framework.

    Dispatches to WdAdapter / CamieAdapter / GenericOnnxAdapter based on
    profile.adapter_family. This lets us add new tagger families without
    touching engine_factory — only registering the new family in
    adapters/__init__.py FAMILY_REGISTRY and adding a profile JSON.
    """
    from .adapters import get_adapter_class
    from .backends.onnx_backend import OnnxBackendSession

    model_id = config.get("model", "SmilingWolf/wd-swinv2-tagger-v3")
    profile = TaggerRegistry.get().resolve_any(model_id)
    if profile is None:
        raise LookupError(
            f"No builtin profile found for model_id={model_id!r}. "
            f"Available: {[p.model_id for p in TaggerRegistry.get().list_profiles()]}"
        )

    adapter_cls = get_adapter_class(profile.adapter_family)
    logger.info(
        "Building %s for profile=%s (model_id=%s)",
        adapter_cls.__name__, profile.id, model_id,
    )

    # Phase 2: get_model_dir_for_profile honours hf_subdir (variant repos).
    from .model_download import get_model_dir_for_profile
    model_dir = get_model_dir_for_profile(profile)
    # Resolve the model and tag-metadata paths from profile.files[] /
    # profile.tag_source. Older code keyed on ".csv" extension; with v2
    # tag_source dispatch the metadata file may be .json (Camie) etc.
    onnx_files = [f.name for f in profile.files if f.name.endswith(".onnx") and f.required]
    if not onnx_files:
        raise ValueError(
            f"profile {profile.id} must declare at least one required "
            f".onnx file in profile.files[]"
        )
    onnx_path = model_dir / onnx_files[0]
    ts = profile.tag_source
    tag_file_name = ts.get("file") or ts.get("tags_file")
    if not isinstance(tag_file_name, str):
        raise ValueError(
            f"profile {profile.id} tag_source must declare 'file' or 'tags_file'"
        )
    # csv_path kwarg name preserved for adapter backward-compat; adapters
    # only use .parent to derive model_dir via load_tag_source.
    csv_path = model_dir / tag_file_name

    backend = OnnxBackendSession(onnx_path)
    # adapter_cls comes from a runtime registry; all ONNX adapters
    # (WdAdapter / GenericOnnxAdapter / CamieAdapter) share this kwargs
    # contract by convention, so cast to Any for the call site.
    return cast(Any, adapter_cls)(
        profile=profile,
        backend=backend,
        csv_path=csv_path,
        thresholds=_thresholds_from_config(config),
    )


def _build_vlm_adapter_via_framework(config: dict[str, Any]) -> Any:
    """Build a VlmAdapter shim wrapping legacy VlmWdTaggerEngine."""
    from .adapters.vlm_adapter import VlmAdapter, build_vlm_profile
    from .engine_vlm import VlmWdTaggerEngine

    legacy = VlmWdTaggerEngine(
        base_url=config.get("vlm_url", "http://localhost:11434"),
        model=config.get("vlm_model", ""),
        timeout=config.get("vlm_timeout", 60),
    )
    profile = build_vlm_profile(
        base_url=config.get("vlm_url", "http://localhost:11434"),
        model_name=config.get("vlm_model", "vlm"),
        timeout=config.get("vlm_timeout", 60),
    )
    return VlmAdapter(profile=profile, legacy_engine=legacy)


def _build_legacy_composite(config: dict[str, Any]) -> Any:
    """Phase 1b: engine_type='both' uses the legacy composite engine.

    Migrated to composite_profiles[] in Phase 3. Building this path uses
    the legacy OnnxWdTaggerEngine + VlmWdTaggerEngine rather than the
    new framework — these two engines are still WdTaggerEngine subclasses
    so legacy callers continue to work.
    """
    from .engine_composite import CompositeWdTaggerEngine
    from .engine_onnx import OnnxWdTaggerEngine
    from .engine_vlm import VlmWdTaggerEngine
    from .model_download import get_model_dir

    model_id = config.get("model", "SmilingWolf/wd-swinv2-tagger-v3")
    profile = TaggerRegistry.get().resolve_any(model_id)
    repo_for_dir = profile.model_id if profile is not None else model_id
    onnx = OnnxWdTaggerEngine(
        model_dir=get_model_dir(repo_for_dir),
        general_threshold=config.get("general_threshold", 0.35),
        character_threshold=config.get("character_threshold", 0.85),
    )
    vlm = VlmWdTaggerEngine(
        base_url=config.get("vlm_url", "http://localhost:11434"),
        model=config.get("vlm_model", ""),
        timeout=config.get("vlm_timeout", 60),
    )
    return CompositeWdTaggerEngine(onnx, vlm)


def get_engine(config: dict[str, Any]) -> Any:
    """Build / fetch a tagger engine for the given config.

    Returns either a TaggerAdapter (new framework, engine_type=onnx|vlm)
    or a WdTaggerEngine (legacy, engine_type=both). Both satisfy the
    same caller contract (tag_image / tag_images_batch / get_name /
    is_available).
    """
    engine_type = config.get("engine_type", "onnx")
    cache = _get_or_build_cache(int(config.get("engine_cache_size", 1)))

    # engine_type=both uses legacy path, no caching for now (Phase 3 migrates)
    if engine_type == "both":
        return _build_legacy_composite(config)

    # New framework path: cache key includes engine_type to avoid mixing
    # onnx / vlm entries in the same slot.
    if engine_type == "vlm":
        cache_key = (
            f"vlm:{config.get('vlm_url', '')}:{config.get('vlm_model', '')}",
            _thresholds_hash(_thresholds_from_config(config)),
        )
        return cache.get(
            key=cache_key,
            builder=lambda: _build_vlm_adapter_via_framework(config),
        )

    # Default: engine_type=onnx
    cache_key = (
        config.get("model", "SmilingWolf/wd-swinv2-tagger-v3"),
        _thresholds_hash(_thresholds_from_config(config)),
    )
    adapter = cache.get(
        key=cache_key,
        builder=lambda: _build_onnx_adapter_via_framework(config),
    )
    logger.info("Created WD-Tagger engine: %s", adapter.get_name())
    return adapter
