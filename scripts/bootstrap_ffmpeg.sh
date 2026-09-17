#!/usr/bin/env bash
# Provide ffmpeg without root privileges.
#
# - Linux: print distro-specific install hint and exit non-zero. We do NOT
#   auto-download on Linux because a package-manager install (apt/dnf/pacman)
#   gives the user proper updates, codec coverage, and integration with system
#   media tooling. Static tarballs work but mismatch the system in subtle ways.
# - macOS: download evermeet.cx's static ffmpeg + ffprobe binaries into
#   ./bin/ffmpeg/ so callers can prepend that directory to PATH.
#
# Called from start.sh ONLY after the user has consented (or set
# YU_AUTO_INSTALL_FFMPEG=1). Exit 0 means ffmpeg is now usable from
# ./bin/ffmpeg/ (macOS) or no further action (already installed). Exit 2 means
# Linux was detected and the caller should fall through with a warning.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN_DIR="$PROJECT_ROOT/bin"
FFMPEG_DIR="$BIN_DIR/ffmpeg"
FFMPEG_BIN="$FFMPEG_DIR/ffmpeg"

if [ -x "$FFMPEG_BIN" ]; then
    if "$FFMPEG_BIN" -version >/dev/null 2>&1; then
        echo "[OK] ffmpeg already present at $FFMPEG_BIN"
        "$FFMPEG_BIN" -version | head -n 1
        exit 0
    else
        echo "[INFO] ffmpeg binary present but not executable (wrong arch?), re-downloading..."
        rm -f "$FFMPEG_BIN" "$FFMPEG_DIR/ffprobe"
    fi
fi

os=$(uname -s)

if [ "$os" = "Linux" ]; then
    # Detect distro family from /etc/os-release and print the matching command.
    pkg_hint="(your distro's package manager)"
    if [ -r /etc/os-release ]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        case "${ID:-}${ID_LIKE:-}" in
            *debian*|*ubuntu*) pkg_hint="sudo apt update && sudo apt install ffmpeg" ;;
            *fedora*|*rhel*|*centos*) pkg_hint="sudo dnf install ffmpeg" ;;
            *arch*|*manjaro*) pkg_hint="sudo pacman -S ffmpeg" ;;
            *suse*) pkg_hint="sudo zypper install ffmpeg" ;;
            *alpine*) pkg_hint="sudo apk add ffmpeg" ;;
            *)
                if command -v apt &>/dev/null; then pkg_hint="sudo apt install ffmpeg"
                elif command -v dnf &>/dev/null; then pkg_hint="sudo dnf install ffmpeg"
                elif command -v pacman &>/dev/null; then pkg_hint="sudo pacman -S ffmpeg"
                elif command -v zypper &>/dev/null; then pkg_hint="sudo zypper install ffmpeg"
                elif command -v apk &>/dev/null; then pkg_hint="sudo apk add ffmpeg"
                fi
                ;;
        esac
    fi
    echo "[INFO] Linux detected. Install ffmpeg via your distro:"
    echo "         ${pkg_hint}"
    echo "       Then re-run start.sh. (Auto-download is not used on Linux to"
    echo "       avoid mismatching system media libraries.)"
    exit 2
fi

if [ "$os" != "Darwin" ]; then
    echo "[ERROR] Unsupported OS for ffmpeg auto-install: $os" >&2
    exit 1
fi

# --- macOS path ---
arch=$(uname -m)
case "$arch" in
    x86_64) ;;
    arm64|aarch64) ;;
    *) echo "[ERROR] Unsupported macOS architecture: $arch" >&2; exit 1 ;;
esac

mkdir -p "$FFMPEG_DIR"

# On arm64, evermeet.cx provides x86_64-only binaries; use Homebrew instead.
if [ "$arch" = "arm64" ] || [ "$arch" = "aarch64" ]; then
    if command -v brew &>/dev/null; then
        BREW_FFMPEG=$(brew --prefix ffmpeg 2>/dev/null)/bin/ffmpeg
        BREW_FFPROBE=$(brew --prefix ffmpeg 2>/dev/null)/bin/ffprobe
        if [ ! -x "$BREW_FFMPEG" ]; then
            echo "[INFO] Installing ffmpeg via Homebrew (arm64 native)..."
            brew install ffmpeg
            BREW_FFMPEG=$(brew --prefix ffmpeg 2>/dev/null)/bin/ffmpeg
            BREW_FFPROBE=$(brew --prefix ffmpeg 2>/dev/null)/bin/ffprobe
        fi
        if [ -x "$BREW_FFMPEG" ]; then
            ln -sf "$BREW_FFMPEG" "$FFMPEG_DIR/ffmpeg"
            ln -sf "$BREW_FFPROBE" "$FFMPEG_DIR/ffprobe"
            echo "[OK] ffmpeg symlinked from Homebrew: $BREW_FFMPEG"
            "$FFMPEG_DIR/ffmpeg" -version | head -n 1
            exit 0
        fi
    fi
    echo "[WARNING] Homebrew not available on arm64; falling back to evermeet.cx (x86_64, requires Rosetta 2)."
fi

# x86_64 (or arm64 fallback): download from evermeet.cx.
tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

fetch() {
    local url="$1" out="$2"
    if command -v curl &>/dev/null; then
        curl -LsSf "$url" -o "$out"
    elif command -v wget &>/dev/null; then
        wget -q "$url" -O "$out"
    else
        echo "[ERROR] curl or wget is required to download ffmpeg" >&2
        exit 1
    fi
}

echo "[INFO] Downloading ffmpeg (evermeet.cx, latest release, x86_64)..."
fetch "https://evermeet.cx/ffmpeg/getrelease/zip" "$tmpdir/ffmpeg.zip"
echo "[INFO] Downloading ffprobe (evermeet.cx, latest release, x86_64)..."
fetch "https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip" "$tmpdir/ffprobe.zip"

unzip -q -o "$tmpdir/ffmpeg.zip" -d "$tmpdir/ffmpeg_extract"
unzip -q -o "$tmpdir/ffprobe.zip" -d "$tmpdir/ffprobe_extract"

# evermeet zips contain a single binary at the archive root.
ffmpeg_src=$(find "$tmpdir/ffmpeg_extract" -type f -name "ffmpeg" | head -n 1)
ffprobe_src=$(find "$tmpdir/ffprobe_extract" -type f -name "ffprobe" | head -n 1)
if [ -z "$ffmpeg_src" ] || [ -z "$ffprobe_src" ]; then
    echo "[ERROR] Unexpected archive layout (binaries not found)" >&2
    exit 1
fi

mv "$ffmpeg_src" "$FFMPEG_DIR/ffmpeg"
mv "$ffprobe_src" "$FFMPEG_DIR/ffprobe"
chmod +x "$FFMPEG_DIR/ffmpeg" "$FFMPEG_DIR/ffprobe"

# Strip Gatekeeper quarantine if present so Finder-launched contexts work too.
xattr -d com.apple.quarantine "$FFMPEG_DIR/ffmpeg" 2>/dev/null || true
xattr -d com.apple.quarantine "$FFMPEG_DIR/ffprobe" 2>/dev/null || true

echo "[OK] ffmpeg installed: $FFMPEG_DIR/ffmpeg"
"$FFMPEG_DIR/ffmpeg" -version | head -n 1
