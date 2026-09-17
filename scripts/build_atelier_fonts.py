"""Atelier System font subset builder.

Downloads Fraunces / Inter / JetBrains Mono Variable fonts from Google Fonts
GitHub releases and emits Latin-Extended subsets as woff2 to
ui/default/static/fonts/atelier/.

Run: uv run python scripts/build_atelier_fonts.py
"""
from __future__ import annotations

import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path("ui/default/static/fonts/atelier")
OUT.mkdir(parents=True, exist_ok=True)

SOURCES = {
    "Fraunces-VariableFont.ttf": (
        "https://github.com/undercasetype/Fraunces/raw/master/fonts/variable/"
        "Fraunces[SOFT,WONK,opsz,wght].ttf"
    ),
    "Inter-VariableFont.ttf": (
        "https://github.com/rsms/inter/raw/master/docs/font-files/"
        "InterVariable.ttf"
    ),
    "JetBrainsMono-VariableFont.ttf": (
        "https://github.com/JetBrains/JetBrainsMono/raw/master/fonts/variable/"
        "JetBrainsMono[wght].ttf"
    ),
}

# Latin Basic + Latin-1 Supplement + Latin Extended-A + Latin Extended-B
# + General Punctuation + Superscripts/Subscripts + Currency Symbols
UNICODES = "U+0000-00FF,U+0100-017F,U+0180-024F,U+2000-206F,U+2070-209F,U+20A0-20CF"


def _download(url: str, dest: Path) -> None:
    """Download with explicit User-Agent (GitHub raw blocks default urllib UA on some paths)."""
    # quote path component so brackets in filenames survive
    parsed = urllib.parse.urlsplit(url)
    safe_path = urllib.parse.quote(parsed.path, safe="/")
    encoded = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, safe_path, parsed.query, parsed.fragment))
    req = urllib.request.Request(encoded, headers={"User-Agent": "atelier-font-builder/1.0"})
    with urllib.request.urlopen(req) as resp, dest.open("wb") as fh:
        fh.write(resp.read())


def main() -> None:
    for fname, url in SOURCES.items():
        src = OUT / fname
        if not src.exists():
            print(f"Downloading {fname}")
            _download(url, src)
        out_name = fname.replace(".ttf", ".subset.woff2")
        cmd = [
            "pyftsubset", str(src),
            f"--unicodes={UNICODES}",
            "--flavor=woff2",
            "--with-zopfli",
            "--layout-features=*",
            f"--output-file={OUT / out_name}",
        ]
        print(f"Subsetting {fname}")
        subprocess.run(cmd, check=True)
        src.unlink()
    print("Done.")


if __name__ == "__main__":
    main()
