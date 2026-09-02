"""Low-level WebP RIFF chunk parsing helpers."""

from pathlib import Path


def parse_webp_chunks(path: Path) -> list[tuple[bytes, bytes]]:
    chunks: list[tuple[bytes, bytes]] = []
    with path.open("rb") as f:
        riff = f.read(12)
        if len(riff) < 12 or riff[0:4] != b"RIFF" or riff[8:12] != b"WEBP":
            return chunks

        while True:
            hdr = f.read(8)
            if len(hdr) < 8:
                break
            fourcc = hdr[0:4]
            ln = int.from_bytes(hdr[4:8], "little", signed=False)
            data = f.read(ln)
            if ln % 2 == 1:
                f.read(1)
            chunks.append((fourcc, data))

    return chunks
