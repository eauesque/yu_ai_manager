#!/usr/bin/env bash
# Regenerate scripts/uv-checksums.txt — the pinned SHA-256 manifest for the
# project-scoped uv binary. Run this ONLY when bumping the pinned uv version
# (DEFAULT_UV_VERSION in bootstrap_uv.sh / bootstrap_uv.ps1).
#
# For every supported release triple it:
#   1. downloads the official archive AND its published .sha256 from GitHub,
#   2. verifies the downloaded archive matches the published .sha256,
#   3. extracts it and records the SHA-256 of the uv/uvx binary inside.
#
# The resulting manifest is consumed by:
#   - bootstrap_uv.sh / bootstrap_uv.ps1 (verify the archive before install)
#   - scripts/pre_push_check.py           (verify the installed bin/uv binary)
#
# This script needs network and is a manual maintenance tool; it never runs in
# the sandboxed pre-push hook.
set -euo pipefail

VERSION="${1:-}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ -z "$VERSION" ]; then
    VERSION=$(sed -n 's/^DEFAULT_UV_VERSION="\(.*\)"/\1/p' "$ROOT/scripts/bootstrap_uv.sh")
fi
if [ -z "$VERSION" ]; then
    echo "[ERROR] could not determine uv version (pass as arg 1)" >&2
    exit 1
fi

OUT="$ROOT/scripts/uv-checksums.txt"
BASE="https://github.com/astral-sh/uv/releases/download/$VERSION"

# Triples mirror those handled by bootstrap_uv.sh (tar.gz) and bootstrap_uv.ps1 (zip).
TAR_TRIPLES="x86_64-unknown-linux-gnu aarch64-unknown-linux-gnu armv7-unknown-linux-gnueabihf x86_64-apple-darwin aarch64-apple-darwin"
ZIP_TRIPLES="x86_64-pc-windows-msvc aarch64-pc-windows-msvc i686-pc-windows-msvc"

sha256_of() { shasum -a 256 "$1" | awk '{print $1}'; }

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

{
    echo "# uv pinned-binary checksums (SHA-256). DO NOT EDIT BY HAND."
    echo "# Regenerate via: bash scripts/update_uv_checksums.sh"
    echo "# Columns: <version> <triple> <kind:archive|binary> <sha256> <artifact>"
    echo "version $VERSION"
} > "$OUT"

emit_triple() {
    local triple="$1" ext="$2" archive="uv-$1.$2"
    local url="$BASE/$archive"
    echo "[INFO] $archive" >&2
    curl -LsS --fail --max-time 120 -o "$tmp/$archive" "$url"
    curl -LsS --fail --max-time 60 -o "$tmp/$archive.sha256" "$url.sha256"
    local published actual
    published=$(awk '{print $1}' "$tmp/$archive.sha256")
    actual=$(sha256_of "$tmp/$archive")
    if [ "$published" != "$actual" ]; then
        echo "[ERROR] $archive: published $published != downloaded $actual" >&2
        exit 1
    fi
    echo "$VERSION $triple archive $actual $archive" >> "$OUT"

    local exedir="$tmp/x-$triple"
    mkdir -p "$exedir"
    if [ "$ext" = "tar.gz" ]; then
        tar -xzf "$tmp/$archive" -C "$exedir"
        local inner
        inner=$(find "$exedir" -maxdepth 1 -type d -name "uv-*" | head -n1)
        [ -n "$inner" ] || inner="$exedir"
        echo "$VERSION $triple binary $(sha256_of "$inner/uv") uv" >> "$OUT"
        [ -f "$inner/uvx" ] && echo "$VERSION $triple binary $(sha256_of "$inner/uvx") uvx" >> "$OUT"
    else
        unzip -qo "$tmp/$archive" -d "$exedir"
        echo "$VERSION $triple binary $(sha256_of "$exedir/uv.exe") uv.exe" >> "$OUT"
        [ -f "$exedir/uvx.exe" ] && echo "$VERSION $triple binary $(sha256_of "$exedir/uvx.exe") uvx.exe" >> "$OUT"
    fi
}

for t in $TAR_TRIPLES; do emit_triple "$t" "tar.gz"; done
for t in $ZIP_TRIPLES; do emit_triple "$t" "zip"; done

echo "[OK] wrote $OUT"
