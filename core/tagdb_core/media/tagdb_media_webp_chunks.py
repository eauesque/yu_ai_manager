"""Chunk-based WebP metadata extraction."""

import contextlib
from pathlib import Path

from core.tagdb_core.media.tagdb_media_webp_exif import parse_exif_user_comment


def extract_webp_text_chunks(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        with path.open("rb") as f:
            riff = f.read(12)
            if len(riff) < 12 or riff[0:4] != b"RIFF" or riff[8:12] != b"WEBP":
                return out

            all_chunks: list[tuple[bytes, bytes]] = []

            while True:
                hdr = f.read(8)
                if len(hdr) < 8:
                    break
                fourcc = hdr[0:4]
                ln = int.from_bytes(hdr[4:8], "little", signed=False)
                data = f.read(ln)
                if ln % 2 == 1:
                    f.read(1)

                all_chunks.append((fourcc, data))

            for fourcc, data in all_chunks:
                if fourcc == b"EXIF":
                    uc = parse_exif_user_comment(data)
                    if uc:
                        out["exif:UserComment"] = uc
                        if ("Steps:" in uc) and ("Negative prompt:" in uc or "Sampler:" in uc):
                            out.setdefault("parameters", uc)
                            out.setdefault("Parameters", uc)

                    if not uc:
                        # A probe: the exception IS the answer (not this encoding).
                        with contextlib.suppress(Exception):
                            text = data.decode("utf-8", errors="ignore").strip()
                            if len(text) > 10 and ("Steps:" in text or "Negative prompt:" in text):
                                out["exif:raw"] = text
                                if "Steps:" in text:
                                    out.setdefault("parameters", text)
                                    out.setdefault("Parameters", text)

                        with contextlib.suppress(Exception):
                            text = data.decode("utf-16", errors="ignore").strip()
                            if len(text) > 10 and ("Steps:" in text or "Negative prompt:" in text):
                                out["exif:raw"] = text
                                if "Steps:" in text:
                                    out.setdefault("parameters", text)
                                    out.setdefault("Parameters", text)

                elif fourcc == b"XMP ":
                    # A probe: a chunk that is not XMP simply does not parse.
                    with contextlib.suppress(Exception):
                        x = data.decode("utf-8", errors="ignore").strip()
                        if x:
                            out["xmp"] = x
                            import re

                            desc_match = re.search(
                                r"<(?:dc:description|exif:UserComment)[^>]*>(.*?)</(?:dc:description|exif:UserComment)>",
                                x,
                                re.DOTALL,
                            )
                            if desc_match:
                                desc = desc_match.group(1).strip()
                                desc = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", desc, flags=re.DOTALL)
                                desc = desc.strip()
                                if desc:
                                    out["Description"] = desc
                                    if ("Steps:" in desc) and ("Negative prompt:" in desc or "Sampler:" in desc):
                                        out.setdefault("parameters", desc)
                                        out.setdefault("Parameters", desc)

                elif fourcc not in (b"VP8 ", b"VP8L", b"VP8X", b"ALPH", b"ANIM", b"ANMF", b"ICCP"):
                    # A probe over an unrecognised chunk.
                    with contextlib.suppress(Exception):
                        text = data.decode("utf-8", errors="ignore").strip()
                        if len(text) > 20 and any(
                            kw in text for kw in ["Steps:", "Negative prompt:", "Sampler:", "prompt", "workflow"]
                        ):
                            chunk_name = fourcc.decode("ascii", errors="replace").strip()
                            out[f"chunk:{chunk_name}"] = text
                            if "Steps:" in text:
                                out.setdefault("parameters", text)
                                out.setdefault("Parameters", text)
                            elif "prompt" in text.lower():
                                out.setdefault("prompt", text)

            return out
    except Exception:
        return out
