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
# Pass --force (or FORCE=1) to re-download over an already-installed binary
# -- e.g. after bumping DEFAULT_UV_VERSION above.

set -euo pipefail

DEFAULT_UV_VERSION="0.11.8"
UV_VERSION="${UV_VERSION:-$DEFAULT_UV_VERSION}"
FORCE="${FORCE:-0}"
for arg in "$@"; do
    [ "$arg" = "--force" ] && FORCE=1
done

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN_DIR="$PROJECT_ROOT/bin"
UV_BIN="$BIN_DIR/uv"
CHECKSUM_MANIFEST="$PROJECT_ROOT/scripts/uv-checksums.txt"

mkdir -p "$BIN_DIR"

# Serialize whole runs of this script (e.g. a manual --force racing
# security_audit.py's 24h timer). Unique staging filenames (below) stop two
# concurrent runs from corrupting each other's bytes, but without a lock they
# can still interleave: run A's uv swap could land between run B's uv swap
# and B's uvx swap, pairing a stale uv with a new uvx (or vice versa) if
# UV_VERSION ever differs between callers. The lock makes the whole
# download+verify+swap sequence transactional across concurrent invocations.
#
# `mkdir` is the lock primitive (atomic, POSIX, no flock/GNU-only dependency
# -- stock macOS ships neither GNU flock nor GNU seq, and its fractional-
# second `sleep` support is not guaranteed either, so none of the three are
# used here). A record of the holder's PID *and* process start time lets a
# later run detect and clear a stale lock left behind by a crashed/killed
# holder, instead of waiting out the full timeout on every run forever --
# without ever mistaking a still-running holder for a dead one:
#   - bare PID liveness (`kill -0`) is not enough on its own: given enough
#     elapsed time the recorded PID can be recycled by a wholly unrelated
#     but genuinely live process, making `kill -0` report "alive" forever
#     and wedge every future run permanently.
#   - reclaiming purely by age is not safe either: a real holder can
#     legitimately still be running past any fixed age threshold (a slow
#     network mid-download), and yanking its lock out from under it lets a
#     second run start concurrently, defeating the whole point of the lock.
#   - the fix is PID *identity*, not just liveness: record `ps -o lstart=`
#     for the holder PID alongside it. On the next attempt, if that PID no
#     longer exists, or exists but its start time no longer matches, it is
#     provably a different process (dead-and-reused or never restarted) and
#     the lock is safe to reclaim. If the start time still matches, it is
#     provably the SAME still-running process, so we never touch the lock
#     no matter how old it is -- we just keep waiting (and eventually time
#     out with a message asking for manual inspection, rather than guess).
LOCK_DIR="$BIN_DIR/.bootstrap_uv.lock"
LOCK_PID_FILE="$LOCK_DIR/pid"
holder_start_time() {
    ps -o lstart= -p "$1" 2>/dev/null | tr -s ' ' || true
}
lock_acquired=0
for ((_attempt = 0; _attempt < 150; _attempt++)); do
    if mkdir "$LOCK_DIR" 2>/dev/null; then
        lock_acquired=1
        break
    fi
    if [ -f "$LOCK_PID_FILE" ] && [ -n "$(find "$LOCK_DIR" -maxdepth 0 -mmin +2 2>/dev/null)" ]; then
        holder=$(sed -n '1p' "$LOCK_PID_FILE" 2>/dev/null || true)
        recorded_start=$(sed -n '2p' "$LOCK_PID_FILE" 2>/dev/null || true)
        reclaim=0
        if [ -n "$holder" ]; then
            if ! kill -0 "$holder" 2>/dev/null; then
                reclaim=1
            elif [ -n "$recorded_start" ]; then
                current_start=$(holder_start_time "$holder")
                if [ -n "$current_start" ] && [ "$current_start" != "$recorded_start" ]; then
                    reclaim=1
                fi
            fi
        fi
        if [ "$reclaim" = "1" ]; then
            echo "[WARN] Removing stale lock $LOCK_DIR (>2min old, PID $holder is dead or belongs to a different process)" >&2
            rm -rf "$LOCK_DIR"
            continue
        fi
    fi
    sleep 1
done
if [ "$lock_acquired" != "1" ]; then
    echo "[ERROR] Timed out waiting for $LOCK_DIR -- another bootstrap_uv.sh run appears stuck. Remove it manually if no such run is actually in progress." >&2
    exit 1
fi
printf '%s\n%s\n' "$$" "$(holder_start_time "$$")" > "$LOCK_PID_FILE"
trap 'rm -rf "$LOCK_DIR" 2>/dev/null || true' EXIT

if [ -x "$UV_BIN" ] && [ "$FORCE" != "1" ]; then
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

tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir" 2>/dev/null || true; rm -rf "$LOCK_DIR" 2>/dev/null || true' EXIT

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

# Stage into BIN_DIR (same filesystem as UV_BIN) before the final swap. tmpdir
# is often tmpfs (/tmp) on a different mount than BIN_DIR, so a direct
# `mv "$inner_dir/uv" "$UV_BIN"` can silently become a cross-device copy; if
# that copy is interrupted (disk full, killed), the currently-installed,
# working uv binary is destroyed mid-write with nothing left to roll back to.
# Copying into BIN_DIR first means a failure there never touches UV_BIN, and
# the final `mv` (same filesystem) is an atomic rename.
# Staging names include $$ (PID) so two concurrent invocations (e.g. a manual
# --force alongside security_audit.py's timer) never share the same
# in-progress file and corrupt each other's copy.
uv_stage="$BIN_DIR/.uv.new.$$"
cp "$inner_dir/uv" "$uv_stage"
chmod +x "$uv_stage"
mv "$uv_stage" "$UV_BIN"
if [ -f "$inner_dir/uvx" ]; then
    uvx_stage="$BIN_DIR/.uvx.new.$$"
    cp "$inner_dir/uvx" "$uvx_stage"
    chmod +x "$uvx_stage"
    mv "$uvx_stage" "$BIN_DIR/uvx"
fi

echo "[OK] uv installed: $UV_BIN"
"$UV_BIN" --version
