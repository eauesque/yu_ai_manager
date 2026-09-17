#!/usr/bin/env python3
"""Compare OCR capability scores across the Python and Rust implementations."""

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def python_table(path: Path) -> dict[str, dict[str, int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "_DEFAULT_CAPABILITIES"
            for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            if isinstance(value, dict):
                return value
    raise ValueError("_DEFAULT_CAPABILITIES assignment not found")


def balanced(text: str, start: int, opening: str, closing: str) -> str:
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise ValueError(f"unclosed {opening}")


def routes_table(path: Path) -> dict[str, dict[str, int]]:
    text = path.read_text(encoding="utf-8")
    function = text.index("fn builtin_ocr_profiles()")
    macro = text.index("json!(", function)
    start = text.index("{", macro)
    source = balanced(text, start, "{", "}")
    return json.loads(re.sub(r",(\s*[}\]])", r"\1", source))


def router_table(path: Path) -> dict[str, dict[str, int]]:
    text = path.read_text(encoding="utf-8")
    start = text.index("const BUILTIN_SCORES")
    start = text.index("= [", start) + 2
    source = balanced(text, start, "[", "]")
    entries = re.findall(r'\(\s*"([^"]+)",\s*&\[(.*?)\],?\s*\)', source, re.DOTALL)
    if not entries:
        raise ValueError("BUILTIN_SCORES entries not found")
    result = {}
    for model, scores in entries:
        pairs = re.findall(r'\("([^"]+)",\s*(\d+)\)', scores)
        if not pairs:
            raise ValueError(f"scores not found for {model}")
        result[model] = {task: int(score) for task, score in pairs}
    return result


def compare(expected: dict[str, dict[str, int]], actual: dict[str, dict[str, int]], name: str) -> list[str]:
    errors = []
    for model in sorted(expected.keys() | actual.keys()):
        if model not in expected or model not in actual:
            errors.append(f"{name}: model {model!r} missing from {'Python' if model not in expected else name}")
            continue
        for task in sorted(expected[model].keys() | actual[model].keys()):
            left, right = expected[model].get(task), actual[model].get(task)
            if left != right:
                errors.append(f"{name}: {model} {task}: Python={left!r}, {name}={right!r}")
    return errors


def main() -> int:
    try:
        expected = python_table(ROOT / "extensions/builtin_ocr/core_impl/router.py")
        errors = compare(expected, routes_table(ROOT / "crates/yu-server/src/routes/ocr.rs"), "routes/ocr.rs")
        errors += compare(expected, router_table(ROOT / "crates/yu-server/src/ocr/router.rs"), "ocr/router.rs")
    except (OSError, SyntaxError, ValueError, json.JSONDecodeError) as error:
        print(f"cannot read OCR score table: {error}", file=sys.stderr)
        return 2
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"OCR score tables match: {len(expected)} models")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
