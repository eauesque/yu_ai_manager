"""Send-side parity: `build_request_body` must agree across Python and Rust.

The extraction harness compares what the two implementations *read*. Nothing
compared what they *send* -- and a divergence there is the silent kind: NovelAI
answers 200 either way and only the image differs.

Both implementations are pure functions, so the seam is their output, not the
network. **The upstream base URL is deliberately left unconfigurable**: opening
it to env/config so a test could point it at a local sink would also let an
attacker point a real token at any host they like.

Rust side emits its half via `cargo test -p yu-server -- --ignored
emit_request_body_fixtures`, which writes the same JSON shape this script
produces for Python.

Usage:
    uv run python scripts/verify_nai_send_parity.py            # compare
    uv run python scripts/verify_nai_send_parity.py --emit-python  # write ours
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

FIXTURES = REPO / "crates" / "yu-server" / "tests" / "fixtures" / "nai_send_parity"
PY_OUT = FIXTURES / "python.json"
RS_OUT = FIXTURES / "rust.json"

# Each case is (name, kwargs). The names are shared with the Rust emitter so a
# mismatch names the case rather than an index.
#
# `use_coords` is derived from character centers on both sides today, and the
# two derivations disagree -- see the cases marked "known divergence". They are
# included on purpose: a harness that only feeds agreeing inputs proves nothing.
CASES: list[tuple[str, dict[str, Any]]] = [
    ("minimal", {"prompt": "a cat", "negative_prompt": "bad"}),
    (
        "v5_continuous_coords",
        {
            "prompt": "2girls",
            "negative_prompt": "bad",
            "model": "nai-diffusion-5-full",
            "characters": [
                {"prompt": "girl", "negative": "naked", "center": {"x": 0.495, "y": 0.519}},
                {"prompt": "boy", "negative": "", "center": {"x": 0.528, "y": 0.258}},
            ],
        },
    ),
    (
        "v4_grid_coords",
        {
            "prompt": "2girls",
            "negative_prompt": "bad",
            "model": "nai-diffusion-4-5-full",
            "characters": [
                {"prompt": "girl", "negative": "", "center": {"x": 0.5, "y": 0.5}},
                {"prompt": "boy", "negative": "", "center": {"x": 0.3, "y": 0.5}},
            ],
        },
    ),
    (
        "ai_choice_no_centers",
        {
            "prompt": "2girls",
            "negative_prompt": "bad",
            "characters": [{"prompt": "girl", "negative": ""}],
        },
    ),
    # Known divergence: Python scans every character, Rust skips empty prompts.
    (
        "empty_prompt_with_center",
        {
            "prompt": "x",
            "negative_prompt": "y",
            "characters": [{"prompt": "", "negative": "", "center": {"x": 0.2, "y": 0.2}}],
        },
    ),
    # Known divergence: an empty center object.
    (
        "nonempty_prompt_empty_center",
        {
            "prompt": "x",
            "negative_prompt": "y",
            "characters": [{"prompt": "a", "negative": "", "center": {}}],
        },
    ),
    # The per-generation character cap: V5 keeps 22, V4.5 keeps 6. The captions
    # are numbered so a truncation at the wrong index changes the payload.
    (
        "v5_character_cap",
        {
            "prompt": "crowd",
            "negative_prompt": "bad",
            "model": "nai-diffusion-5-full",
            "characters": [{"prompt": f"char{i}", "negative": f"bad{i}"} for i in range(24)],
        },
    ),
    (
        "v45_character_cap",
        {
            "prompt": "crowd",
            "negative_prompt": "bad",
            "model": "nai-diffusion-4-5-full",
            "characters": [{"prompt": f"char{i}", "negative": f"bad{i}"} for i in range(24)],
        },
    ),
]

# Fields that legitimately differ per call and would drown the real signal.
VOLATILE = {"seed"}


def _strip(body: Any) -> Any:
    if isinstance(body, dict):
        return {k: _strip(v) for k, v in sorted(body.items()) if k not in VOLATILE}
    if isinstance(body, list):
        return [_strip(v) for v in body]
    return body


def emit_python() -> dict[str, Any]:
    from extensions.builtin_nai_bridge.core_impl.nai_params import build_request_body

    out: dict[str, Any] = {}
    for name, kwargs in CASES:
        body = build_request_body(**kwargs)
        # Python returns the body dict directly; Rust returns (body, seed, fmt).
        out[name] = _strip(body if isinstance(body, dict) else body[0])
    return out


def compare() -> int:
    if not PY_OUT.exists() or not RS_OUT.exists():
        print(f"missing fixture(s): {PY_OUT.exists()=} {RS_OUT.exists()=}")
        print("run --emit-python and the Rust emitter first")
        return 2

    py = json.loads(PY_OUT.read_text(encoding="utf-8"))
    rs = json.loads(RS_OUT.read_text(encoding="utf-8"))

    names = sorted(set(py) | set(rs))
    failures: list[str] = []
    for name in names:
        if name not in py:
            failures.append(f"{name}: missing on the Python side")
            continue
        if name not in rs:
            failures.append(f"{name}: missing on the Rust side")
            continue
        if py[name] != rs[name]:
            diff_keys = sorted(
                k for k in set(py[name]) | set(rs[name])
                if py[name].get(k) != rs[name].get(k)
            )
            for k in diff_keys:
                failures.append(
                    f"{name}.{k}: python={json.dumps(py[name].get(k), ensure_ascii=False)} "
                    f"rust={json.dumps(rs[name].get(k), ensure_ascii=False)}"
                )

    if failures:
        print(f"send-side parity: FAIL ({len(failures)} difference(s))")
        for f in failures:
            print(f"  - {f}")
        return 1

    print(f"send-side parity: PASS ({len(names)} case(s))")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit-python", action="store_true")
    args = ap.parse_args()

    if args.emit_python:
        FIXTURES.mkdir(parents=True, exist_ok=True)
        PY_OUT.write_text(
            json.dumps(emit_python(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {PY_OUT.relative_to(REPO)}")
        return 0

    return compare()


if __name__ == "__main__":
    raise SystemExit(main())
