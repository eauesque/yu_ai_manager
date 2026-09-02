#!/bin/bash
# ==========================================
# YU AI Manager - Rust server release build
# ==========================================
# Usage:
#   ./scripts/build-rust-server.sh                         # Release build (GPU EP auto-detected)
#   ./scripts/build-rust-server.sh --hailo DIR             # Build with HailoRT (specify include dir)
#   ./scripts/build-rust-server.sh --gpu-feature coreml   # Force a specific ORT GPU EP feature
#   ./scripts/build-rust-server.sh --gpu-feature ""       # CPU-only (disable auto-detect)
#   ./scripts/build-rust-server.sh --no-strip              # Skip binary strip
#   ./scripts/build-rust-server.sh check                   # Prerequisites check only
#
# GPU EP auto-detection (overridable via --gpu-feature or ORT_GPU_FEATURE env):
#   macOS -> coreml | Linux+ROCm -> rocm | Linux+CUDA -> cuda | Linux+Intel -> openvino
# ==========================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CRATES_DIR="$PROJECT_ROOT/crates"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info() { echo -e "${CYAN}[INFO]${NC} $1"; }
ok()   { echo -e "${GREEN}[OK]${NC}   $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ── locale ────────────────────────────────────────────────────────────────────
_LOCALE="${LC_ALL:-${LC_MESSAGES:-${LANG:-en_US.UTF-8}}}"
_LANG="${_LOCALE%%[._@]*}"
case "$_LOCALE" in
    zh_TW*|zh_HK*|zh_Hant*) _LANG="zh_TW" ;;
    zh_CN*|zh_SG*|zh_Hans*) _LANG="zh_CN" ;;
esac

# ── i18n ─────────────────────────────────────────────────────────────────────
case "$_LANG" in
    ja)
        MSG_CHECK_CARGO="cargo を確認中..."
        MSG_NO_CARGO="cargo が見つかりません。https://rustup.rs/ からインストールしてください"
        MSG_CHECK_OPENSSL="OpenSSL ヘッダーを確認中..."
        MSG_NO_OPENSSL="OpenSSL dev ヘッダーが見つかりません — インストール: apt install libssl-dev"
        MSG_CHECK_HAILO="HailoRT ヘッダーを確認中..."
        MSG_NO_HAILO="hailo/hailort.hpp が見つかりません"
        MSG_HAILO_AUTO="HAILO_INCLUDE_DIR 未指定 — build.rs がヘッダーを自動検出します（未検出時は stub）"
        MSG_BUILDING="yu-server をリリースビルド中..."
        MSG_STRIPPED="バイナリを strip しました"
        MSG_DONE="ビルド完了:"
        MSG_PREREQS_OK="全ての前提条件を満たしています"
        MSG_PREREQS_MISSING="一部の前提条件が不足しています"
        MSG_PREREQ_FAIL="前提条件を満たしていません — 先に check を実行してください"
        MSG_BINARY_MISSING="ビルド成功しましたがバイナリが見つかりません"
        MSG_UNKNOWN_ARG="不明な引数"
        ;;
    ko)
        MSG_CHECK_CARGO="cargo 확인 중..."
        MSG_NO_CARGO="cargo를 찾을 수 없습니다. https://rustup.rs/ 에서 설치하세요"
        MSG_CHECK_OPENSSL="OpenSSL 헤더 확인 중..."
        MSG_NO_OPENSSL="OpenSSL dev 헤더를 찾을 수 없습니다 — 설치: apt install libssl-dev"
        MSG_CHECK_HAILO="HailoRT 헤더 확인 중..."
        MSG_NO_HAILO="hailo/hailort.hpp를 찾을 수 없습니다"
        MSG_HAILO_AUTO="HAILO_INCLUDE_DIR 미설정 — build.rs가 헤더를 자동 감지합니다 (미검출 시 stub)"
        MSG_BUILDING="yu-server 릴리스 빌드 중..."
        MSG_STRIPPED="바이너리 strip 완료"
        MSG_DONE="빌드 완료:"
        MSG_PREREQS_OK="모든 필수 조건을 충족합니다"
        MSG_PREREQS_MISSING="일부 필수 조건이 누락되었습니다"
        MSG_PREREQ_FAIL="필수 조건 미충족 — 먼저 check를 실행하세요"
        MSG_BINARY_MISSING="빌드 성공했지만 바이너리를 찾을 수 없습니다"
        MSG_UNKNOWN_ARG="알 수 없는 인수"
        ;;
    zh_TW)
        MSG_CHECK_CARGO="正在確認 cargo..."
        MSG_NO_CARGO="找不到 cargo。請從 https://rustup.rs/ 安裝"
        MSG_CHECK_OPENSSL="正在確認 OpenSSL 標頭..."
        MSG_NO_OPENSSL="找不到 OpenSSL dev 標頭 — 安裝: apt install libssl-dev"
        MSG_CHECK_HAILO="正在確認 HailoRT 標頭..."
        MSG_NO_HAILO="找不到 hailo/hailort.hpp"
        MSG_HAILO_AUTO="未設定 HAILO_INCLUDE_DIR — build.rs 將自動偵測標頭（未找到時使用 stub）"
        MSG_BUILDING="正在編譯 yu-server（release）..."
        MSG_STRIPPED="已 strip 二進位檔"
        MSG_DONE="編譯完成:"
        MSG_PREREQS_OK="所有前置條件均已滿足"
        MSG_PREREQS_MISSING="部分前置條件缺失"
        MSG_PREREQ_FAIL="前置條件不滿足 — 請先執行 check"
        MSG_BINARY_MISSING="編譯成功但找不到二進位檔"
        MSG_UNKNOWN_ARG="未知參數"
        ;;
    zh_CN)
        MSG_CHECK_CARGO="正在确认 cargo..."
        MSG_NO_CARGO="找不到 cargo。请从 https://rustup.rs/ 安装"
        MSG_CHECK_OPENSSL="正在确认 OpenSSL 头文件..."
        MSG_NO_OPENSSL="找不到 OpenSSL dev 头文件 — 安装: apt install libssl-dev"
        MSG_CHECK_HAILO="正在确认 HailoRT 头文件..."
        MSG_NO_HAILO="找不到 hailo/hailort.hpp"
        MSG_HAILO_AUTO="未设置 HAILO_INCLUDE_DIR — build.rs 将自动检测头文件（未找到时使用 stub）"
        MSG_BUILDING="正在编译 yu-server（release）..."
        MSG_STRIPPED="已 strip 二进制文件"
        MSG_DONE="编译完成:"
        MSG_PREREQS_OK="所有前置条件均已满足"
        MSG_PREREQS_MISSING="部分前置条件缺失"
        MSG_PREREQ_FAIL="前置条件不满足 — 请先执行 check"
        MSG_BINARY_MISSING="编译成功但找不到二进制文件"
        MSG_UNKNOWN_ARG="未知参数"
        ;;
    *)
        MSG_CHECK_CARGO="Checking cargo..."
        MSG_NO_CARGO="cargo not found — install from https://rustup.rs/"
        MSG_CHECK_OPENSSL="Checking OpenSSL headers..."
        MSG_NO_OPENSSL="OpenSSL dev headers not found — install: apt install libssl-dev"
        MSG_CHECK_HAILO="Checking HailoRT headers..."
        MSG_NO_HAILO="hailo/hailort.hpp not found under specified dir"
        MSG_HAILO_AUTO="HAILO_INCLUDE_DIR not set — build.rs will auto-detect headers (stub if absent)"
        MSG_BUILDING="Building yu-server (release)..."
        MSG_STRIPPED="Binary stripped"
        MSG_DONE="Build complete:"
        MSG_PREREQS_OK="All prerequisites satisfied"
        MSG_PREREQS_MISSING="Some prerequisites missing"
        MSG_PREREQ_FAIL="Prerequisites not met — run: $0 check"
        MSG_BINARY_MISSING="Build succeeded but binary not found"
        MSG_UNKNOWN_ARG="Unknown argument"
        ;;
esac

# ── parse args ────────────────────────────────────────────────────────────────
HAILO_DIR=""
DO_STRIP=1
COMMAND="build"
GPU_FEATURE="__auto__"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --hailo)       shift; HAILO_DIR="${1:-}"; shift ;;
        --no-strip)    DO_STRIP=0; shift ;;
        --gpu-feature) shift; GPU_FEATURE="${1:-}"; shift ;;
        check|build)   COMMAND="$1"; shift ;;
        *) err "$MSG_UNKNOWN_ARG: $1" ;;
    esac
done

# Auto-detect Hailo from standard include paths (mirrors build.rs logic)
if [[ -z "$HAILO_DIR" ]]; then
    for _d in /usr/local/include /usr/include; do
        if [[ -f "$_d/hailo/hailort.hpp" ]]; then
            HAILO_DIR="$_d"
            break
        fi
    done
fi

# Resolve GPU EP feature: CLI arg > ORT_GPU_FEATURE env > auto-detect
_detect_gpu_feature() {
    case "$(uname -s)" in
        Darwin) echo "coreml" ;;
        Linux)
            if [[ -d /opt/rocm ]] || command -v rocm-smi &>/dev/null; then
                echo "rocm"
            elif command -v nvidia-smi &>/dev/null; then
                echo "cuda"
            elif lspci 2>/dev/null | grep -qi "intel.*vga\|intel.*display"; then
                echo "openvino"
            fi
            ;;
    esac
}
if [[ "$GPU_FEATURE" == "__auto__" ]]; then
    GPU_FEATURE="${ORT_GPU_FEATURE:-$(_detect_gpu_feature)}"
fi

# ── prerequisites ─────────────────────────────────────────────────────────────
check_prereqs() {
    local result=0

    info "$MSG_CHECK_CARGO"
    if ! command -v cargo &>/dev/null; then
        warn "$MSG_NO_CARGO"; result=1
    else
        ok "cargo $(cargo --version 2>/dev/null | head -1)"
    fi

    info "$MSG_CHECK_OPENSSL"
    local ssl_found=0
    if [[ -n "${OPENSSL_DIR:-}" ]] && [[ -f "$OPENSSL_DIR/include/openssl/ssl.h" ]]; then
        ok "openssl ($OPENSSL_DIR)"; ssl_found=1
    elif pkg-config --exists openssl 2>/dev/null; then
        ok "openssl $(pkg-config --modversion openssl 2>/dev/null)"; ssl_found=1
    elif [[ -f /usr/include/openssl/ssl.h ]] || [[ -f /usr/local/include/openssl/ssl.h ]]; then
        ok "openssl (system headers)"; ssl_found=1
    fi
    if [[ $ssl_found -eq 0 ]]; then
        warn "$MSG_NO_OPENSSL"  # advisory only — openssl-sys has its own detection
    fi

    if [[ -n "$HAILO_DIR" ]]; then
        info "$MSG_CHECK_HAILO ($HAILO_DIR)"
        if [[ -f "$HAILO_DIR/hailo/hailort.hpp" ]]; then
            ok "HailoRT headers found"
        else
            warn "$MSG_NO_HAILO"; result=1
        fi
    else
        info "$MSG_HAILO_AUTO"
    fi

    return $result
}

if [[ "$COMMAND" == "check" ]]; then
    check_prereqs \
        && ok "$MSG_PREREQS_OK" \
        || { warn "$MSG_PREREQS_MISSING"; exit 1; }
    exit 0
fi

# ── build ─────────────────────────────────────────────────────────────────────
check_prereqs || err "$MSG_PREREQ_FAIL"

info "$MSG_BUILDING"
cd "$CRATES_DIR"

BUILD_ENV=()
[[ -n "$HAILO_DIR" ]] && BUILD_ENV+=("HAILO_INCLUDE_DIR=$HAILO_DIR")

# native-dialog: OS folder-picker (rfd) for /api/tools/select-folder. Always on —
# without it the picker silently no-ops (returns headless_unsupported).
FEATURES="native-dialog"
[[ -n "$GPU_FEATURE" ]] && FEATURES="$FEATURES,$GPU_FEATURE" && info "GPU EP: $GPU_FEATURE"

env "${BUILD_ENV[@]}" cargo build --release -p yu-server --features "$FEATURES"

# Respect CARGO_TARGET_DIR if set
TARGET_DIR="${CARGO_TARGET_DIR:-$CRATES_DIR/target}"
BINARY="$TARGET_DIR/release/yu-server"
[[ -f "$BINARY" ]] || err "$MSG_BINARY_MISSING: $BINARY"

if [[ $DO_STRIP -eq 1 ]] && command -v strip &>/dev/null; then
    strip "$BINARY"
    ok "$MSG_STRIPPED"
fi

SIZE=$(du -sh "$BINARY" | cut -f1)
ok "$MSG_DONE $BINARY ($SIZE)"
