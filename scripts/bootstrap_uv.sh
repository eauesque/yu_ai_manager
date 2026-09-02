#!/usr/bin/env bash
# Download a project-scoped uv binary into ./bin/uv.
#
# Called from start.sh when bin/uv is missing. Idempotent: if the binary
# already exists this script exits without doing anything (start.sh skips
# invocation entirely in that case).
#
# Source: https://github.com/astral-sh/uv/releases/download/<UV_VERSION>/uv-<triple>.tar.gz
# The Unix tarballs unpack to a directory named uv-<triple>/{uv,uvx}; we move
# those two binaries into bin/ and discard the wrapping directory.
#
# Version is pinned (not "latest") so a future uv release with breaking
# behavior can't silently change `uv sync --extra` semantics underneath us.
# Override with `UV_VERSION=<ver> bash scripts/bootstrap_uv.sh` to test newer.

set -euo pipefail

DEFAULT_UV_VERSION="0.11.8"
UV_VERSION="${UV_VERSION:-$DEFAULT_UV_VERSION}"

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN_DIR="$PROJECT_ROOT/bin"
UV_BIN="$BIN_DIR/uv"
CHECKSUM_MANIFEST="$PROJECT_ROOT/scripts/uv-checksums.txt"

if [ -x "$UV_BIN" ]; then
    echo "[OK] uv already present at $UV_BIN"
    exit 0
fi

# Detect target triple. uv release filenames mirror Rust target triples.
os=$(uname -s)
arch=$(uname -m)

case "$os" in
    Linux)
        case "$arch" in
            x86_64)         triple="x86_64-unknown-linux-gnu" ;;
            aarch64|arm64)  triple="aarch64-unknown-linux-gnu" ;;
            armv7l)         triple="armv7-unknown-linux-gnueabihf" ;;
            *) echo "[ERROR] Unsupported Linux architecture: $arch" >&2; exit 1 ;;
        esac
        ;;
    Darwin)
        case "$arch" in
            x86_64)         triple="x86_64-apple-darwin" ;;
            arm64|aarch64)  triple="aarch64-apple-darwin" ;;
            *) echo "[ERROR] Unsupported macOS architecture: $arch" >&2; exit 1 ;;
        esac
        ;;
    *) echo "[ERROR] Unsupported OS: $os" >&2; exit 1 ;;
esac

url="https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-$triple.tar.gz"
echo "[INFO] Downloading uv $UV_VERSION ($triple) from $url"

sha256_file() {
    if command -v shasum &>/dev/null; then
        shasum -a 256 "$1" | awk '{print $1}'
    elif command -v sha256sum &>/dev/null; then
        sha256sum "$1" | awk '{print $1}'
    else
        echo "[ERROR] shasum or sha256sum is required to verify uv" >&2
        exit 1
    fi
}

mkdir -p "$BIN_DIR"
tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

if command -v curl &>/dev/null; then
    curl -LsSf "$url" -o "$tmpdir/uv.tar.gz"
elif command -v wget &>/dev/null; then
    wget -q "$url" -O "$tmpdir/uv.tar.gz"
else
    echo "[ERROR] curl or wget is required to download uv" >&2
    exit 1
fi

expected=""
if [ -f "$CHECKSUM_MANIFEST" ]; then
    expected=$(awk -v v="$UV_VERSION" -v t="$triple" '$1==v && $2==t && $3=="archive"{print $4}' "$CHECKSUM_MANIFEST")
fi

if [ -z "$expected" ]; then
    if [ "${UV_ALLOW_UNVERIFIED:-}" = "1" ]; then
        echo "[WARN] uv archive checksum is not registered; continuing because UV_ALLOW_UNVERIFIED=1" >&2
    else
        echo "[ERROR] checksum 未登録の uv バージョン。scripts/update_uv_checksums.sh で登録するか UV_ALLOW_UNVERIFIED=1 を指定" >&2
        exit 1
    fi
else
    actual=$(sha256_file "$tmpdir/uv.tar.gz")
    if [ "$actual" != "$expected" ]; then
        echo "[ERROR] uv アーカイブの checksum 不一致（供給網改竄の疑い）" >&2
        echo "  expected: $expected" >&2
        echo "  actual:   $actual" >&2
        exit 1
    fi
fi

tar -xzf "$tmpdir/uv.tar.gz" -C "$tmpdir"
# Tarball contains a single directory uv-<triple>/ with uv and uvx inside.
inner_dir=$(find "$tmpdir" -maxdepth 1 -type d -name "uv-*" | head -n 1)
if [ -z "$inner_dir" ]; then
    echo "[ERROR] Unexpected archive layout" >&2
    exit 1
fi
mv "$inner_dir/uv" "$UV_BIN"
[ -f "$inner_dir/uvx" ] && mv "$inner_dir/uvx" "$BIN_DIR/uvx"
chmod +x "$UV_BIN" "$BIN_DIR/uvx" 2>/dev/null || true

echo "[OK] uv installed: $UV_BIN"
"$UV_BIN" --version
