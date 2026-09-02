"""Manual regression: legacy OnnxWdTaggerEngine vs new WdAdapter on REAL WD models.

Run before merging Phase 1a:

    uv run python scripts/manual_regression_wd.py \\
        --model-dir cache/wd_tagger/SmilingWolf_wd-swinv2-tagger-v3 \\
        --profile-id wd_swinv2_v3 \\
        --image path/to/test.jpg

Repeats the assertions from tests/test_adapter_wd_regression.py with real
models and real images. Expected to pass with the same atol/rtol tolerance.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from extensions.builtin_wd_tagger.core_impl.adapters.wd_adapter import WdAdapter
from extensions.builtin_wd_tagger.core_impl.backends.onnx_backend import (
    OnnxBackendSession,
)
from extensions.builtin_wd_tagger.core_impl.engine_onnx import OnnxWdTaggerEngine
from extensions.builtin_wd_tagger.core_impl.registry import TaggerRegistry


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model-dir", type=Path, required=True,
        help="Directory with model.onnx + selected_tags.csv",
    )
    parser.add_argument(
        "--profile-id", type=str, required=True,
        help="Builtin profile id (e.g. wd_swinv2_v3)",
    )
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--general-threshold", type=float, default=0.35)
    parser.add_argument("--character-threshold", type=float, default=0.85)
    args = parser.parse_args()

    legacy = OnnxWdTaggerEngine(
        model_dir=args.model_dir,
        general_threshold=args.general_threshold,
        character_threshold=args.character_threshold,
    )

    profile = TaggerRegistry.get().resolve(args.profile_id)
    backend = OnnxBackendSession(args.model_dir / "model.onnx")
    new_adapter = WdAdapter(
        profile=profile,
        backend=backend,
        csv_path=args.model_dir / "selected_tags.csv",
        thresholds={
            "general": args.general_threshold,
            "character": args.character_threshold,
            "rating": 0.0,
        },
    )

    legacy_result = legacy.tag_image(str(args.image))
    new_result = new_adapter.tag_image(str(args.image))

    legacy_tags = [t.tag for t in legacy_result.tags]
    new_tags = [t.tag for t in new_result.tags]
    assert legacy_tags == new_tags, (
        f"TAG SET MISMATCH:\n  legacy: {legacy_tags}\n  new:    {new_tags}"
    )

    legacy_confs = np.array(
        [t.confidence for t in legacy_result.tags], dtype=np.float32,
    )
    new_confs = np.array(
        [t.confidence for t in new_result.tags], dtype=np.float32,
    )
    np.testing.assert_allclose(
        legacy_confs, new_confs, atol=1e-5, rtol=1e-4,
    )

    assert legacy_result.rating == new_result.rating

    print(f"PASS: {len(legacy_tags)} tags, rating={legacy_result.rating}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
