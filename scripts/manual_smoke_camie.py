"""Manual smoke for Camie Tagger v2 via the new framework.

Run before merging Phase 2a:

    # Download Camie model first (if not already cached):
    uv run python -c "
    from extensions.builtin_wd_tagger.core_impl.registry import TaggerRegistry
    from extensions.builtin_wd_tagger.core_impl.model_download import (
        download_model_for_profile,
    )
    profile = TaggerRegistry.get().resolve('camie_tagger_v2')
    print('Downloading to', download_model_for_profile(profile).cache_dir)
    "

    # Then smoke:
    uv run python scripts/manual_smoke_camie.py --image path/to/anime.jpg

Compares output against the profile's expected categories. If the
result list looks unreasonable (no tags / nonsense tags / very low
confidences), the profile JSON's preprocess_spec or default_thresholds
likely needs adjustment — verify against the HF model card at
https://huggingface.co/Camais03/camie-tagger-v2.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from core.paths import init_app_paths
from extensions.builtin_wd_tagger.core_impl.engine_factory import (
    clear_engine_cache,
    get_engine,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--image", type=Path, required=True,
        help="Path to a test image (anime / illustration recommended).",
    )
    parser.add_argument(
        "--top-n", type=int, default=20,
        help="Print top-N tags per category (default 20).",
    )
    args = parser.parse_args()

    if not args.image.exists():
        print(f"ERROR: image not found: {args.image}")
        return 1

    # Standalone scripts need to bootstrap paths before any module that
    # touches cache_path / data_path can run. Idempotent if web_ui already
    # called it.
    init_app_paths()

    config = {
        "model": "Camais03/camie-tagger-v2",
        "engine_type": "onnx",
        "general_threshold": 0.55,
        "character_threshold": 0.85,
    }

    clear_engine_cache()
    engine = get_engine(config)
    print(f"Engine: {engine.get_name()}")
    print(f"Image:  {args.image}")
    print()

    result = engine.tag_image(str(args.image))
    print(f"Rating: {result.rating}")
    print(f"Total tags above threshold: {len(result.tags)}")
    print()

    by_category: dict[str, list] = {}
    for t in result.tags:
        by_category.setdefault(t.category, []).append(t)

    for category in sorted(by_category):
        tags = sorted(by_category[category], key=lambda x: x.confidence, reverse=True)
        print(f"=== {category} (top {args.top_n} of {len(tags)}) ===")
        for t in tags[: args.top_n]:
            print(f"  {t.confidence:.4f}  {t.tag}")
        print()

    print("OK — review the output above against expectation. If tags look")
    print("nonsense or confidences are clustered at extremes, adjust")
    print("camie_tagger_v2.json preprocess_spec / default_thresholds.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
