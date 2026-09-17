#!/usr/bin/env bash
# Download a project-scoped Node.js distribution into ./bin/node/.
#
# Called from start.sh when neither a system `node` nor `bin/node/bin/node`
# is found AND the user has consented to the auto-install. The downloaded
# tree mirrors the official Node distribution layout (bin/, lib/, share/,
# include/) so callers only need to prepend ./bin/node/bin to PATH.
#
# Source: https://nodejs.org/dist/<NODE_VERSION>/node-<NODE_VERSION>-<platform>.tar.xz
# Version is pinned (not "latest") so corepack/pnpm versions stay deterministic.
# Override with `NODE_VERSION=vX.Y.Z bash scripts/bootstrap_node.sh`.

set -euo pipefail

DEFAULT_NODE_VERSION="v22.11.0"
NODE_VERSION="${NODE_VERSION:-$DEFAULT_NODE_VERSION}"

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN_DIR="$PROJECT_ROOT/bin"
NODE_DIR="$BIN_DIR/node"
NODE_BIN="$NODE_DIR/bin/node"

if [ -x "$NODE_BIN" ]; then
    echo "[OK] Node.js already present at $NODE_BIN"
    "$NODE_BIN" --version
    exit 0
fi

# Detect platform suffix used by Node release filenames.
os=$(uname -s)
arch=$(uname -m)

case "$os" in
    Linux)
        case "$arch" in
            x86_64)         platform="linux-x64" ;;
            aarch64|arm64)  platform="linux-arm64" ;;
            armv7l)         platform="linux-armv7l" ;;
            *) echo "[ERROR] Unsupported Linux architecture: $arch" >&2; exit 1 ;;
        esac
        ;;
    Darwin)
        case "$arch" in
            x86_64)         platform="darwin-x64" ;;
            arm64|aarch64)  platform="darwin-arm64" ;;
            *) echo "[ERROR] Unsupported macOS architecture: $arch" >&2; exit 1 ;;
        esac
        ;;
    *) echo "[ERROR] Unsupported OS: $os" >&2; exit 1 ;;
esac

archive="node-${NODE_VERSION}-${platform}.tar.xz"
url="https://nodejs.org/dist/${NODE_VERSION}/${archive}"
echo "[INFO] Downloading Node.js ${NODE_VERSION} (${platform}) from ${url}"

mkdir -p "$BIN_DIR"
tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

if command -v curl &>/dev/null; then
    curl -LsSf "$url" -o "$tmpdir/node.tar.xz"
elif command -v wget &>/dev/null; then
    wget -q "$url" -O "$tmpdir/node.tar.xz"
else
    echo "[ERROR] curl or wget is required to download Node.js" >&2
    exit 1
fi

# Archive top-level directory is node-<version>-<platform>/. Extract there,
# then move/rename it to ./bin/node/ (replacing any partial previous attempt).
tar -xJf "$tmpdir/node.tar.xz" -C "$tmpdir"
inner_dir=$(find "$tmpdir" -maxdepth 1 -type d -name "node-${NODE_VERSION}-${platform}" | head -n 1)
if [ -z "$inner_dir" ]; then
    echo "[ERROR] Unexpected archive layout (expected node-${NODE_VERSION}-${platform}/)" >&2
    exit 1
fi

# Replace any partial install (clean slate). bin/ itself is shared with uv etc.
rm -rf "$NODE_DIR"
mv "$inner_dir" "$NODE_DIR"

if [ ! -x "$NODE_BIN" ]; then
    echo "[ERROR] Node binary not found after extraction at $NODE_BIN" >&2
    exit 1
fi

echo "[OK] Node.js installed: $NODE_BIN"
"$NODE_BIN" --version

# Enable corepack so `pnpm` becomes available without a separate install.
# corepack ships with Node 16+. Failures here are non-fatal — the launcher
# falls back to npm if pnpm cannot be activated.
COREPACK="$NODE_DIR/bin/corepack"
if [ -x "$COREPACK" ]; then
    if "$COREPACK" enable pnpm 2>/dev/null; then
        echo "[OK] corepack enabled pnpm"
    else
        echo "[WARN] corepack enable pnpm failed (npm fallback will be used)"
    fi
fi
