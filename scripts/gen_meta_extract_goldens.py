"""Generate meta-extract conformance goldens from Python builtin parsers.

Usage:
    UV_CACHE_DIR=tmp/.uv-cache ./bin/uv run python scripts/gen_meta_extract_goldens.py

Reads each synthetic PNG fixture, runs the corresponding Python builtin parser's
on_scan_file_impl / on_scan_file, applies the field mapping from format_map.yaml,
normalizes fields, and writes crates/meta-extract/tests/goldens/<parser>.json.
"""
from __future__ import annotations

import json
import struct
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from meta_extract_normalize import normalize_fields

FIXTURES = REPO / "crates" / "meta-extract" / "tests" / "fixtures" / "inspect_parity"
OUT = REPO / "crates" / "meta-extract" / "tests" / "goldens"
FORMAT_MAP_PATH = OUT / "format_map.yaml"


@dataclass
class ExtractedMetadataStub:
    meta_source: str
    format: str
    raw_prompt: str | None = None
    raw_negative: str | None = None
    raw_meta_json: str | None = None
    tag_source: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class DetailSectionStub:
    title: str
    display_type: str
    content: Any
    copyable: bool = False


def install_runtime_stub() -> None:
    """Avoid importing the full extension runtime when only parser data classes are needed."""
    for name in (
        "core.extensions_core.runtime",
        "core.extensions_core.lifecycle.runtime",
    ):
        module = ModuleType(name)
        module.ExtractedMetadata = ExtractedMetadataStub
        module.DetailSection = DetailSectionStub
        sys.modules[name] = module


def load_format_map() -> dict[str, str]:
    mappings: dict[str, str] = {}
    in_mappings = False
    for raw_line in FORMAT_MAP_PATH.read_text().splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line == "mappings:":
            in_mappings = True
            continue
        if in_mappings and line.startswith("  ") and ":" in line:
            key, value = line.strip().split(":", 1)
            mappings[key.strip()] = value.strip().strip('"')
    if not mappings:
        raise ValueError(f"No mappings found in {FORMAT_MAP_PATH}")
    return mappings


def _read_png_chunks(png_path: Path) -> dict[str, str]:
    """Read tEXt chunks from a PNG file using stdlib only."""
    data = png_path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "Not a PNG"
    chunks: dict[str, str] = {}
    pos = 8
    while pos < len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        chunk_type = data[pos + 4 : pos + 8]
        chunk_data = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if chunk_type == b"tEXt":
            null = chunk_data.index(b"\x00")
            key = chunk_data[:null].decode("latin-1")
            val = chunk_data[null + 1 :].decode("latin-1", errors="replace")
            chunks[key] = val
    return chunks


def run_a1111(fixture: Path) -> object | None:
    chunks = _read_png_chunks(fixture)
    sys.path.insert(0, str(REPO / "extensions" / "builtin_a1111"))
    from a1111_parser_hooks import on_scan_file_impl

    return on_scan_file_impl(str(fixture), None, chunks)


def run_comfyui(fixture: Path) -> object | None:
    chunks = _read_png_chunks(fixture)
    sys.path.insert(0, str(REPO / "extensions" / "builtin_comfyui"))
    from comfyui_parser_scan import on_scan_file_impl

    return on_scan_file_impl(str(fixture), None, chunks)


def run_nai_v3(fixture: Path) -> object | None:
    chunks = _read_png_chunks(fixture)
    sys.path.insert(0, str(REPO / "extensions" / "builtin_novelai_v3"))
    from novelai_v3_hooks import on_scan_file_impl

    return on_scan_file_impl(str(fixture), None, chunks)


def run_nai_v4(fixture: Path) -> object | None:
    chunks = _read_png_chunks(fixture)
    sys.path.insert(0, str(REPO / "extensions" / "builtin_novelai_v4"))
    from novelai_v4 import on_scan_file

    return on_scan_file(str(fixture), None, chunks)


PARSERS: list[tuple[str, str, Callable[[Path], object | None]]] = [
    ("a1111", "a1111.png", run_a1111),
    ("comfy", "comfyui_conform.png", run_comfyui),
    ("nai_v3", "novelai_v3_conform.png", run_nai_v3),
    ("nai_v4", "novelai_v4_conform.png", run_nai_v4),
]


def main() -> None:
    install_runtime_stub()
    OUT.mkdir(parents=True, exist_ok=True)
    fmt_map = load_format_map()

    for parser_id, fixture_name, runner in PARSERS:
        fixture = FIXTURES / fixture_name
        if not fixture.exists():
            print(f"SKIP {parser_id}: fixture not found: {fixture}")
            continue

        result = runner(fixture)
        if result is None:
            print(f"ERROR {parser_id}: parser returned None for {fixture_name}")
            sys.exit(1)

        py_format = result.format
        rust_format = fmt_map.get(py_format)
        if rust_format is None:
            print(f"ERROR {parser_id}: Python format '{py_format}' not in format_map.yaml")
            sys.exit(1)

        positive_source = result.tag_source if parser_id == "a1111" else result.raw_prompt
        normed = normalize_fields(positive_source, result.raw_negative, result.raw_meta_json)

        golden = {
            "parser": parser_id,
            "fixture": f"fixtures/inspect_parity/{fixture_name}",
            "python_format_raw": py_format,
            "positive": normed["positive"],
            "negative": normed["negative"],
            "raw_meta": normed["raw_meta"],
            "format_rust": rust_format,
        }

        out_path = OUT / f"{parser_id}.json"
        out_path.write_text(json.dumps(golden, indent=2, ensure_ascii=False) + "\n")
        print(f"wrote {out_path.relative_to(REPO)}")


if __name__ == "__main__":
    main()
