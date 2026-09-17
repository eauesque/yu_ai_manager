"""PNG text chunk extraction from files."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_png_text_chunks(path: Path) -> dict[str, str]:
    import struct
    import zlib

    out: dict[str, str] = {}
    try:
        with path.open("rb") as f:
            sig = f.read(8)
            if sig != b"\x89PNG\r\n\x1a\n":
                return out

            while True:
                header = f.read(8)
                if len(header) < 8:
                    break
                length, ctype = struct.unpack(">I4s", header)
                chunk_data = f.read(length)
                f.read(4)
                ctype_s = ctype.decode("ascii", errors="ignore")

                if ctype_s == "tEXt":
                    if b"\x00" in chunk_data:
                        k, v = chunk_data.split(b"\x00", 1)
                        key = k.decode("latin-1", errors="ignore")
                        try:
                            val = v.decode("utf-8", errors="ignore")
                        except Exception:
                            val = v.decode("latin-1", errors="ignore")
                        if val:
                            out[key] = val

                elif ctype_s == "zTXt":
                    try:
                        p0 = chunk_data.find(b"\x00")
                        if p0 > 0 and p0 + 2 <= len(chunk_data):
                            key = chunk_data[:p0].decode("latin-1", errors="ignore")
                            comp_method = chunk_data[p0 + 1]
                            comp_data = chunk_data[p0 + 2 :]
                            if comp_method == 0:
                                raw = zlib.decompress(comp_data)
                                val = raw.decode("utf-8", errors="ignore")
                                if val:
                                    out[key] = val
                    except Exception as exc:
                        logger.debug("Failed to parse zTXt chunk: %s", exc)

                elif ctype_s == "iTXt":
                    try:
                        p0 = chunk_data.find(b"\x00")
                        if p0 < 0:
                            continue
                        key = chunk_data[:p0].decode("latin-1", errors="ignore")
                        i = p0 + 1

                        if i >= len(chunk_data):
                            continue
                        comp_flag = chunk_data[i]
                        i += 1
                        if i >= len(chunk_data) or chunk_data[i] != 0:
                            continue
                        i += 1

                        comp_method = chunk_data[i]
                        i += 1
                        if i >= len(chunk_data) or chunk_data[i] != 0:
                            continue
                        i += 1

                        p1 = chunk_data.find(b"\x00", i)
                        if p1 < 0:
                            continue
                        i = p1 + 1

                        p2 = chunk_data.find(b"\x00", i)
                        if p2 < 0:
                            continue
                        i = p2 + 1

                        text_bytes = chunk_data[i:]
                        if comp_flag == 1:
                            if comp_method != 0:
                                continue
                            text_bytes = zlib.decompress(text_bytes)

                        val = text_bytes.decode("utf-8", errors="ignore")
                        if val:
                            out[key] = val
                    except Exception as exc:
                        logger.debug("Failed to parse iTXt chunk: %s", exc)

                if ctype_s == "IEND":
                    break
    except Exception:
        return out
    return out
