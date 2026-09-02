"""Generate synthetic conformance PNG fixtures for meta-extract tests.

Produces three PNGs in crates/meta-extract/tests/fixtures/inspect_parity/:
  comfyui_conform.png - tEXt chunk key="prompt", ComfyUI workflow JSON
  novelai_v4_conform.png - tEXt chunk key="Comment", NovelAI v4 JSON
  novelai_v3_conform.png - tEXt chunks key="Comment" + key="Software"="NovelAI", v3 JSON
"""
from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

OUT = (
    Path(__file__).parent.parent
    / "crates"
    / "meta-extract"
    / "tests"
    / "fixtures"
    / "inspect_parity"
)

PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def _ihdr(width: int = 1, height: int = 1) -> bytes:
    return _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))


def _idat_1x1() -> bytes:
    raw = b"\x00\x00"
    compressed = zlib.compress(raw)
    return _chunk(b"IDAT", compressed)


def _iend() -> bytes:
    return _chunk(b"IEND", b"")


def _text(keyword: str, text: str) -> bytes:
    """tEXt chunk: keyword\\x00text (latin-1)."""
    data = keyword.encode("latin-1") + b"\x00" + text.encode(
        "latin-1",
        errors="replace",
    )
    return _chunk(b"tEXt", data)


def make_png(text_chunks: list[tuple[str, str]]) -> bytes:
    chunks = PNG_SIG + _ihdr() + _idat_1x1()
    for key, val in text_chunks:
        chunks += _text(key, val)
    chunks += _iend()
    return chunks


COMFY_WORKFLOW = json.dumps(
    {
        "1": {
            "class_type": "KSampler",
            "inputs": {
                "positive": ["2", 0],
                "negative": ["3", 0],
                "seed": 42,
                "steps": 20,
                "cfg": 7.0,
                "sampler_name": "euler",
            },
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "masterpiece, best quality, 1girl"},
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "lowres, bad anatomy"},
        },
    },
    separators=(",", ":"),
)

NAI_V4_COMMENT = json.dumps(
    {
        "v4_prompt": {"caption": {"base_caption": "a serene landscape"}},
        "v4_negative_prompt": {"caption": {"base_caption": "ugly, blurry"}},
        "steps": 28,
        "scale": 6.0,
        "seed": 1234567,
        "sampler": "k_euler",
        "noise_schedule": "karras",
    },
    separators=(",", ":"),
)

NAI_V3_COMMENT = json.dumps(
    {
        "prompt": "best quality, 1boy, warrior",
        "uc": "lowres, bad anatomy, worst quality",
        "steps": 28,
        "scale": 7.0,
        "seed": 9999999,
        "sampler": "k_euler_ancestral",
        "noise_schedule": "native",
        "strength": 0.5,
        "cfg_rescale": 0.0,
    },
    separators=(",", ":"),
)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    (OUT / "comfyui_conform.png").write_bytes(make_png([("prompt", COMFY_WORKFLOW)]))
    print("wrote comfyui_conform.png")

    (OUT / "novelai_v4_conform.png").write_bytes(
        make_png(
            [
                ("Software", "NovelAI"),
                ("Comment", NAI_V4_COMMENT),
            ]
        )
    )
    print("wrote novelai_v4_conform.png")

    (OUT / "novelai_v3_conform.png").write_bytes(
        make_png(
            [
                ("Software", "NovelAI"),
                ("Comment", NAI_V3_COMMENT),
            ]
        )
    )
    print("wrote novelai_v3_conform.png")


if __name__ == "__main__":
    main()
