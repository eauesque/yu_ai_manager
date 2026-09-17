"""PNG text chunk parsing helpers for in-memory bytes."""

import contextlib
import logging

logger = logging.getLogger(__name__)


def parse_png_text_chunks(data: bytes) -> dict[str, str]:
    chunks: dict[str, str] = {}
    pos = 8

    while pos < len(data) - 12:
        chunk_len = int.from_bytes(data[pos:pos + 4], "big")
        chunk_type = data[pos + 4:pos + 8].decode("ascii", errors="ignore")
        chunk_data = data[pos + 8:pos + 8 + chunk_len]

        if chunk_type == "tEXt":
            try:
                null_idx = chunk_data.index(b"\x00")
                keyword = chunk_data[:null_idx].decode("latin1")
                text_bytes = chunk_data[null_idx + 1:]
                try:
                    text = text_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    text = text_bytes.decode("latin1", errors="replace")
                chunks[keyword] = text
            except Exception as exc:
                logger.debug("Failed to parse tEXt chunk: %s", exc)

        elif chunk_type == "iTXt":
            try:
                null_idx = chunk_data.index(b"\x00")
                keyword = chunk_data[:null_idx].decode("latin1")
                comp_flag = chunk_data[null_idx + 1] if len(chunk_data) > null_idx + 1 else 0
                comp_method = chunk_data[null_idx + 2] if len(chunk_data) > null_idx + 2 else 0
                rest = chunk_data[null_idx + 3:]
                if b"\x00" in rest:
                    rest = rest[rest.index(b"\x00") + 1:]
                if b"\x00" in rest:
                    rest = rest[rest.index(b"\x00") + 1:]

                if comp_flag == 1 and comp_method == 0:
                    import zlib

                    with contextlib.suppress(zlib.error):
                        rest = zlib.decompress(rest)

                text = rest.decode("utf-8", errors="replace")
                chunks[keyword] = text
            except Exception as exc:
                logger.debug("Failed to parse iTXt chunk: %s", exc)

        pos += 4 + 4 + chunk_len + 4
        if pos > len(data):
            break

    return chunks
