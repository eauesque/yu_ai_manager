"""Generate Python prompt_parse goldens for Rust conformance tests.

Usage:
  UV_CACHE_DIR=tmp_uv_cache bin/uv run python scripts/gen_prompt_parse_goldens.py
"""

from __future__ import annotations

import dataclasses
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from core.parsers.prompt_parse import parse_prompt_to_tags

OUT = REPO / "tests" / "compat_goldens" / "prompt_parse"

DEFAULT_CONFIG: dict[str, Any] = {
    "prompt_syntax": "auto",
    "brace_choice": True,
    "preserve_templates": True,
    "lowercase_tags": True,
}

CASES: list[dict[str, Any]] = [
    {
        "name": "comma_tags",
        "prompt": "1Girl, masterpiece, best quality",
    },
    {
        "name": "break_syntax",
        "prompt": "1girl, BREAK, upper body, <break>, smile",
    },
    {
        "name": "nai_brace_choice",
        "prompt": "1girl, {cat|dog|fox}, outdoors",
    },
    {
        "name": "weighted_parentheses",
        "prompt": "((cat:1.2)), (blue eyes), {soft light}",
        "config": {"prompt_syntax": "sd"},
    },
    {
        "name": "blocked_namespaces",
        "prompt": "model: test, adetailer: face, lora:<lora:test:1>, 1girl",
    },
    {
        "name": "empty_symbol_tags",
        "prompt": ",,, ***, !!!, 1girl",
    },
]


def case_filename(name: str) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")
    if not slug:
        raise ValueError(f"Invalid fixture name: {name!r}")
    return f"{slug}.json"


def merged_config(case: dict[str, Any]) -> dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    config.update(case.get("config", {}))
    return config


def tag_rows(tags: list[tuple[str | None, str, float]]) -> list[dict[str, Any]]:
    return [
        {"namespace": namespace, "tag": tag, "weight": weight}
        for namespace, tag, weight in tags
    ]


def token_rows(tokens: list[Any]) -> list[dict[str, Any]]:
    rows = []
    for token in tokens:
        data = dataclasses.asdict(token)
        rows.append(
            {
                "type": data["token_type"],
                "payload": data["payload"],
                "position": data["position"],
            }
        )
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for case in CASES:
        config = merged_config(case)
        parsed = parse_prompt_to_tags(case["prompt"], config)
        golden = {
            "name": case["name"],
            "prompt": case["prompt"],
            "config": config,
            "expected_tags": tag_rows(parsed.tags),
            "expected_template_tokens": token_rows(parsed.template_tokens),
        }
        out_path = OUT / case_filename(case["name"])
        out_path.write_text(
            json.dumps(golden, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {out_path.relative_to(REPO)}")


if __name__ == "__main__":
    main()
