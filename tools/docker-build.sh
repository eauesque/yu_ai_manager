#!/usr/bin/env bash
# docker-build.sh — YU AI Manager integrated Docker build script
#
# Usage:
#   ./tools/docker-build.sh                      # auto-detect and build
#   ./tools/docker-build.sh --hailo --hailo-wheel ~/hailort/dist/*.whl
#   ./tools/docker-build.sh --platform amd64 --tag v2.86.0
#   ./tools/docker-build.sh --dry-run
#
# Options:
#   --platform amd64|arm64   (default: auto-detected from uname -m)
#   --hailo                  Hailo variant build (Pi5 + AI HAT 2 only)
#   --hailo-wheel <path>     .whl file path (required with --hailo)
#   --tag <name>             Image tag (default: yu-ai-manager:latest)
#   --no-cache               Build without cache
#   --dry-run                Display command only
#   -h, --help               Help
#
# About Hailo wheels:
#   Hailo Runtime Python wheels are not distributed on PyPI.
#   You need to build them from source on a Pi5:
#     cd ~/hailort && cmake -B build && cmake --build build
#     cd hailort/libhailort/bindings/python/platform
#     python setup.py bdist_wheel
#   Built .whl files are output to ~/hailort/dist/ etc.
#   Details: docs/development/development_docs/HAILO_SEMANTIC_SEARCH_DEVLOG.md
set -euo pipefail

# === Auto-detect container runtime (docker / podman) ===
if command -v docker &>/dev/null; then
    RUNTIME=docker
elif command -v podman &>/dev/null; then
    RUNTIME=podman
else
    echo "Error: docker or podman is required" >&2
    exit 1
fi

# === Default values ===
PLATFORM=""
HAILO=false
HAILO_WHEEL=""
TAG="yu-ai-manager:latest"
NO_CACHE=false
DRY_RUN=false

# === Help ===
show_help() {
    sed -n '2,/^set /{ /^#/s/^# \?//p }' "$0"
    exit 0
}

# === Parse arguments ===
while [[ $# -gt 0 ]]; do
    case "$1" in
        --platform)    PLATFORM="$2"; shift 2 ;;
        --hailo)       HAILO=true; shift ;;
        --hailo-wheel) HAILO_WHEEL="$2"; shift 2 ;;
        --tag)         TAG="$2"; shift 2 ;;
        --no-cache)    NO_CACHE=true; shift ;;
        --dry-run)     DRY_RUN=true; shift ;;
        -h|--help)     show_help ;;
        *)             echo "Error: unknown option: $1" >&2; exit 1 ;;
    esac
done

# === Auto-detect platform ===
if [[ -z "$PLATFORM" ]]; then
    ARCH=$(uname -m)
    case "$ARCH" in
        x86_64|amd64)   PLATFORM="amd64" ;;
        aarch64|arm64)  PLATFORM="arm64" ;;
        *)              echo "Error: unsupported architecture: $ARCH" >&2; exit 1 ;;
    esac
    echo "Platform auto-detected: $PLATFORM ($ARCH)"
fi

# === Validation ===
case "$PLATFORM" in
    amd64|arm64) ;;
    *) echo "Error: --platform must be amd64 or arm64" >&2; exit 1 ;;
esac

if $HAILO && [[ "$PLATFORM" != "arm64" ]]; then
    echo "Error: --hailo can only be used on the arm64 platform" >&2
    exit 1
fi

if $HAILO && [[ -z "$HAILO_WHEEL" ]]; then
    echo "Error: --hailo-wheel <path> is required when using --hailo" >&2
    echo "  Hailo wheels are not on PyPI; you must build from source on a Pi5." >&2
    echo "  Details: docs/development/development_docs/HAILO_SEMANTIC_SEARCH_DEVLOG.md" >&2
    exit 1
fi

if [[ -n "$HAILO_WHEEL" ]] && ! $HAILO; then
    echo "Error: --hailo-wheel must be used together with --hailo" >&2
    exit 1
fi

if $HAILO && [[ ! -f "$HAILO_WHEEL" ]]; then
    echo "Error: wheel file not found: $HAILO_WHEEL" >&2
    exit 1
fi

# === Move to project root ===
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# === Copy Hailo wheel + cleanup ===
COPIED_WHEEL=""
cleanup() {
    if [[ -n "$COPIED_WHEEL" && -f "$COPIED_WHEEL" ]]; then
        rm -f "$COPIED_WHEEL"
        echo "Cleanup: removed $COPIED_WHEEL"
    fi
}
trap cleanup EXIT

if $HAILO; then
    WHEEL_BASENAME=$(basename "$HAILO_WHEEL")
    COPIED_WHEEL="docker/hailo_wheel/$WHEEL_BASENAME"
    mkdir -p docker/hailo_wheel
    cp "$HAILO_WHEEL" "$COPIED_WHEEL"
    echo "Copied Hailo wheel: $HAILO_WHEEL -> $COPIED_WHEEL"
fi

# === Determine VARIANT ===
VARIANT="standard"
if $HAILO; then
    VARIANT="hailo"
    # Add suffix to tag for Hailo builds (unless user specified a custom tag)
    if [[ "$TAG" == "yu-ai-manager:latest" ]]; then
        TAG="yu-ai-manager:hailo"
    fi
fi

# === Build command assembly ===
BUILD_CMD=("$RUNTIME" build)
BUILD_CMD+=(--build-arg "VARIANT=$VARIANT")
BUILD_CMD+=(--platform "linux/$PLATFORM")
BUILD_CMD+=(-t "$TAG")

if $NO_CACHE; then
    BUILD_CMD+=(--no-cache)
fi

BUILD_CMD+=(.)

# === Execute ===
echo ""
echo "========================================="
echo " YU AI Manager Container Build ($RUNTIME)"
echo "========================================="
echo " Platform:  $PLATFORM"
echo " Variant:   $VARIANT"
echo " Tag:       $TAG"
echo " No-cache:  $NO_CACHE"
if $HAILO; then
    echo " Hailo whl: $(basename "$HAILO_WHEEL")"
fi
echo "========================================="
echo ""
echo " ${BUILD_CMD[*]}"
echo ""

if $DRY_RUN; then
    echo "(dry-run: execution skipped)"
    exit 0
fi

exec "${BUILD_CMD[@]}"
