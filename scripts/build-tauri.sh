#!/bin/bash
# ==========================================
# YU AI Manager - Tauri build script (Bash)
# ==========================================
# Usage:
#   ./scripts/build-tauri.sh              # Release build
#   ./scripts/build-tauri.sh dev          # Development mode (hot reload)
#   ./scripts/build-tauri.sh check        # Prerequisites check only
# ==========================================

set -euo pipefail

# Move to project root
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

COMMAND=${1:-build}

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC}   $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()   { echo -e "${RED}[ERROR]${NC} $1"; }

# --- Detect locale ---
_LOCALE="${LC_ALL:-${LC_MESSAGES:-${LANG:-en_US.UTF-8}}}"
_LANG="${_LOCALE%%[._@]*}"
case "$_LOCALE" in
    zh_TW*|zh_HK*|zh_Hant*) _LANG="zh_TW" ;;
    zh_CN*|zh_SG*|zh_Hans*) _LANG="zh_CN" ;;
esac

# --- i18n messages ---
case "$_LANG" in
    ja)
        MSG_CHECK_RUST="Rust ツールチェーンを確認中..."
        MSG_CARGO_NOT_FOUND="cargo が見つかりません。https://rustup.rs/ からインストールしてください"
        MSG_CHECK_TAURI="tauri-cli を確認中..."
        MSG_TAURI_NOT_FOUND="tauri-cli が見つかりません。インストール: cargo install tauri-cli"
        MSG_CHECK_PNPM="pnpm を確認中..."
        MSG_PNPM_NOT_FOUND="pnpm が見つかりません。npm フォールバックは利用可能ですが pnpm を推奨します"
        MSG_NO_PKG_MGR="pnpm も npm も見つかりません。Node.js をインストールしてください"
        MSG_CHECK_VENV="Python 環境 (uv / venv) を確認中..."
        MSG_VENV_NOT_FOUND="uv も venv も見つかりません。'uv sync' か 'python3 -m venv venv' を実行してください"
        MSG_CHECK_SRCTAURI="src-tauri/ を確認中..."
        MSG_SRCTAURI_NOT_FOUND="src-tauri/Cargo.toml が見つかりません。プロジェクトルートから実行してください"
        MSG_CHECK_WEBUI="web_ui.py を確認中..."
        MSG_WEBUI_NOT_FOUND="web_ui.py が見つかりません"
        MSG_BUILD_FRONTEND="TypeScript フロントエンドをビルド中..."
        MSG_BUILD_FRONTEND_DONE="フロントエンドのビルド完了"
        MSG_CHECK_PREREQ="前提条件を確認中..."
        MSG_ALL_OK="全ての前提条件を満たしています"
        MSG_SOME_MISSING="一部の前提条件が不足しています"
        MSG_DEV_START="開発モードで起動中..."
        MSG_PREREQ_FAIL="前提条件を満たしていません。先に check を実行してください"
        MSG_CARGO_TAURI_DEV="cargo tauri dev を起動中..."
        MSG_FLASK_AUTO="Flask サーバーは Tauri が自動的に起動します"
        MSG_QUIT_HINT="終了するにはウィンドウを閉じるか Ctrl+C を押してください"
        MSG_RELEASE_START="リリースビルドを開始中..."
        MSG_PREREQ_FAIL_SHORT="前提条件を満たしていません"
        MSG_CARGO_TAURI_BUILD="cargo tauri build を実行中 (時間がかかる場合があります)..."
        MSG_BUILD_DONE="ビルド完了!"
        MSG_ARTIFACTS="成果物:"
        MSG_UNKNOWN_CMD="不明なコマンド"
        MSG_USAGE="使い方: ./scripts/build-tauri.sh [build|bundle|dev|check|clean|help]"
        MSG_HELP_TITLE="YU AI Manager - Tauri ビルド"
        MSG_HELP_USAGE="使い方:"
        MSG_HELP_COMMANDS="コマンド:"
        MSG_HELP_CMD_BUILD="リリースビルド (デフォルト)"
        MSG_HELP_CMD_DEV="開発モード (ホットリロード)"
        MSG_HELP_CMD_CHECK="前提条件チェックのみ"
        MSG_HELP_EXAMPLES="例:"
        MSG_HELP_EX_CHECK="# まず前提条件を確認"
        MSG_HELP_EX_BUILD="# リリースビルド"
        MSG_HELP_EX_DEV="# 開発モード"
        ;;
    ko)
        MSG_CHECK_RUST="Rust 툴체인 확인 중..."
        MSG_CARGO_NOT_FOUND="cargo를 찾을 수 없습니다. https://rustup.rs/ 에서 설치하세요"
        MSG_CHECK_TAURI="tauri-cli 확인 중..."
        MSG_TAURI_NOT_FOUND="tauri-cli를 찾을 수 없습니다. 설치: cargo install tauri-cli"
        MSG_CHECK_PNPM="pnpm 확인 중..."
        MSG_PNPM_NOT_FOUND="pnpm을 찾을 수 없습니다. npm 폴백은 가능하지만 pnpm을 권장합니다"
        MSG_NO_PKG_MGR="pnpm과 npm을 모두 찾을 수 없습니다. Node.js를 설치하세요"
        MSG_CHECK_VENV="Python 환경 (uv / venv) 확인 중..."
        MSG_VENV_NOT_FOUND="uv와 venv 모두 찾을 수 없습니다. 'uv sync' 또는 'python3 -m venv venv'를 실행하세요"
        MSG_CHECK_SRCTAURI="src-tauri/ 확인 중..."
        MSG_SRCTAURI_NOT_FOUND="src-tauri/Cargo.toml을 찾을 수 없습니다. 프로젝트 루트에서 실행하세요"
        MSG_CHECK_WEBUI="web_ui.py 확인 중..."
        MSG_WEBUI_NOT_FOUND="web_ui.py를 찾을 수 없습니다"
        MSG_BUILD_FRONTEND="TypeScript 프론트엔드 빌드 중..."
        MSG_BUILD_FRONTEND_DONE="프론트엔드 빌드 완료"
        MSG_CHECK_PREREQ="사전 요구사항 확인 중..."
        MSG_ALL_OK="모든 사전 요구사항이 충족되었습니다"
        MSG_SOME_MISSING="일부 사전 요구사항이 누락되었습니다"
        MSG_DEV_START="개발 모드로 시작 중..."
        MSG_PREREQ_FAIL="사전 요구사항이 충족되지 않았습니다. 먼저 check를 실행하세요"
        MSG_CARGO_TAURI_DEV="cargo tauri dev 시작 중..."
        MSG_FLASK_AUTO="Flask 서버는 Tauri가 자동으로 시작합니다"
        MSG_QUIT_HINT="종료하려면 창을 닫거나 Ctrl+C를 누르세요"
        MSG_RELEASE_START="릴리스 빌드 시작 중..."
        MSG_PREREQ_FAIL_SHORT="사전 요구사항이 충족되지 않았습니다"
        MSG_CARGO_TAURI_BUILD="cargo tauri build 실행 중 (시간이 걸릴 수 있습니다)..."
        MSG_BUILD_DONE="빌드 완료!"
        MSG_ARTIFACTS="산출물:"
        MSG_UNKNOWN_CMD="알 수 없는 명령"
        MSG_USAGE="사용법: ./scripts/build-tauri.sh [build|bundle|dev|check|clean|help]"
        MSG_HELP_TITLE="YU AI Manager - Tauri 빌드"
        MSG_HELP_USAGE="사용법:"
        MSG_HELP_COMMANDS="명령어:"
        MSG_HELP_CMD_BUILD="릴리스 빌드 (기본값)"
        MSG_HELP_CMD_DEV="개발 모드 (핫 리로드)"
        MSG_HELP_CMD_CHECK="사전 요구사항 확인만"
        MSG_HELP_EXAMPLES="예시:"
        MSG_HELP_EX_CHECK="# 먼저 사전 요구사항 확인"
        MSG_HELP_EX_BUILD="# 릴리스 빌드"
        MSG_HELP_EX_DEV="# 개발 모드"
        ;;
    zh_TW)
        MSG_CHECK_RUST="正在檢查 Rust 工具鏈..."
        MSG_CARGO_NOT_FOUND="找不到 cargo。請從 https://rustup.rs/ 安裝"
        MSG_CHECK_TAURI="正在檢查 tauri-cli..."
        MSG_TAURI_NOT_FOUND="找不到 tauri-cli。安裝指令: cargo install tauri-cli"
        MSG_CHECK_PNPM="正在檢查 pnpm..."
        MSG_PNPM_NOT_FOUND="找不到 pnpm。可使用 npm 替代，但建議使用 pnpm"
        MSG_NO_PKG_MGR="找不到 pnpm 和 npm。請安裝 Node.js"
        MSG_CHECK_VENV="正在檢查 Python 環境 (uv / venv)..."
        MSG_VENV_NOT_FOUND="找不到 uv 或 venv。請執行 'uv sync' 或 'python3 -m venv venv'"
        MSG_CHECK_SRCTAURI="正在檢查 src-tauri/..."
        MSG_SRCTAURI_NOT_FOUND="找不到 src-tauri/Cargo.toml。請從專案根目錄執行"
        MSG_CHECK_WEBUI="正在檢查 web_ui.py..."
        MSG_WEBUI_NOT_FOUND="找不到 web_ui.py"
        MSG_BUILD_FRONTEND="正在建置 TypeScript 前端..."
        MSG_BUILD_FRONTEND_DONE="前端建置完成"
        MSG_CHECK_PREREQ="正在檢查前置條件..."
        MSG_ALL_OK="所有前置條件已滿足"
        MSG_SOME_MISSING="部分前置條件缺失"
        MSG_DEV_START="正在以開發模式啟動..."
        MSG_PREREQ_FAIL="前置條件未滿足。請先執行 check"
        MSG_CARGO_TAURI_DEV="正在啟動 cargo tauri dev..."
        MSG_FLASK_AUTO="Flask 伺服器將由 Tauri 自動啟動"
        MSG_QUIT_HINT="關閉視窗或按 Ctrl+C 即可退出"
        MSG_RELEASE_START="正在開始發行版建置..."
        MSG_PREREQ_FAIL_SHORT="前置條件未滿足"
        MSG_CARGO_TAURI_BUILD="正在執行 cargo tauri build（可能需要一些時間）..."
        MSG_BUILD_DONE="建置完成！"
        MSG_ARTIFACTS="產出物："
        MSG_UNKNOWN_CMD="未知的命令"
        MSG_USAGE="用法: ./scripts/build-tauri.sh [build|bundle|dev|check|clean|help]"
        MSG_HELP_TITLE="YU AI Manager - Tauri 建置"
        MSG_HELP_USAGE="用法："
        MSG_HELP_COMMANDS="命令："
        MSG_HELP_CMD_BUILD="發行版建置（預設）"
        MSG_HELP_CMD_DEV="開發模式（熱重載）"
        MSG_HELP_CMD_CHECK="僅檢查前置條件"
        MSG_HELP_EXAMPLES="範例："
        MSG_HELP_EX_CHECK="# 先檢查前置條件"
        MSG_HELP_EX_BUILD="# 發行版建置"
        MSG_HELP_EX_DEV="# 開發模式"
        ;;
    zh_CN)
        MSG_CHECK_RUST="正在检查 Rust 工具链..."
        MSG_CARGO_NOT_FOUND="找不到 cargo。请从 https://rustup.rs/ 安装"
        MSG_CHECK_TAURI="正在检查 tauri-cli..."
        MSG_TAURI_NOT_FOUND="找不到 tauri-cli。安装命令: cargo install tauri-cli"
        MSG_CHECK_PNPM="正在检查 pnpm..."
        MSG_PNPM_NOT_FOUND="找不到 pnpm。可使用 npm 替代，但建议使用 pnpm"
        MSG_NO_PKG_MGR="找不到 pnpm 和 npm。请安装 Node.js"
        MSG_CHECK_VENV="正在检查 Python 环境 (uv / venv)..."
        MSG_VENV_NOT_FOUND="找不到 uv 或 venv。请执行 'uv sync' 或 'python3 -m venv venv'"
        MSG_CHECK_SRCTAURI="正在检查 src-tauri/..."
        MSG_SRCTAURI_NOT_FOUND="找不到 src-tauri/Cargo.toml。请从项目根目录执行"
        MSG_CHECK_WEBUI="正在检查 web_ui.py..."
        MSG_WEBUI_NOT_FOUND="找不到 web_ui.py"
        MSG_BUILD_FRONTEND="正在构建 TypeScript 前端..."
        MSG_BUILD_FRONTEND_DONE="前端构建完成"
        MSG_CHECK_PREREQ="正在检查前置条件..."
        MSG_ALL_OK="所有前置条件已满足"
        MSG_SOME_MISSING="部分前置条件缺失"
        MSG_DEV_START="正在以开发模式启动..."
        MSG_PREREQ_FAIL="前置条件未满足。请先运行 check"
        MSG_CARGO_TAURI_DEV="正在启动 cargo tauri dev..."
        MSG_FLASK_AUTO="Flask 服务器将由 Tauri 自动启动"
        MSG_QUIT_HINT="关闭窗口或按 Ctrl+C 即可退出"
        MSG_RELEASE_START="正在开始发行版构建..."
        MSG_PREREQ_FAIL_SHORT="前置条件未满足"
        MSG_CARGO_TAURI_BUILD="正在执行 cargo tauri build（可能需要一些时间）..."
        MSG_BUILD_DONE="构建完成！"
        MSG_ARTIFACTS="产出物："
        MSG_UNKNOWN_CMD="未知的命令"
        MSG_USAGE="用法: ./scripts/build-tauri.sh [build|bundle|dev|check|clean|help]"
        MSG_HELP_TITLE="YU AI Manager - Tauri 构建"
        MSG_HELP_USAGE="用法："
        MSG_HELP_COMMANDS="命令："
        MSG_HELP_CMD_BUILD="发行版构建（默认）"
        MSG_HELP_CMD_DEV="开发模式（热重载）"
        MSG_HELP_CMD_CHECK="仅检查前置条件"
        MSG_HELP_EXAMPLES="示例："
        MSG_HELP_EX_CHECK="# 先检查前置条件"
        MSG_HELP_EX_BUILD="# 发行版构建"
        MSG_HELP_EX_DEV="# 开发模式"
        ;;
    *)  # English (default)
        MSG_CHECK_RUST="Checking Rust toolchain..."
        MSG_CARGO_NOT_FOUND="cargo not found. Install from https://rustup.rs/"
        MSG_CHECK_TAURI="Checking tauri-cli..."
        MSG_TAURI_NOT_FOUND="tauri-cli not found. Install with: cargo install tauri-cli"
        MSG_CHECK_PNPM="Checking pnpm..."
        MSG_PNPM_NOT_FOUND="pnpm not found. npm fallback is available but pnpm is recommended"
        MSG_NO_PKG_MGR="Neither pnpm nor npm found. Please install Node.js"
        MSG_CHECK_VENV="Checking Python environment (uv / venv)..."
        MSG_VENV_NOT_FOUND="Neither uv nor venv found. Run 'uv sync' or 'python3 -m venv venv'"
        MSG_CHECK_SRCTAURI="Checking src-tauri/..."
        MSG_SRCTAURI_NOT_FOUND="src-tauri/Cargo.toml not found. Run from the project root"
        MSG_CHECK_WEBUI="Checking web_ui.py..."
        MSG_WEBUI_NOT_FOUND="web_ui.py not found"
        MSG_BUILD_FRONTEND="Building TypeScript frontend..."
        MSG_BUILD_FRONTEND_DONE="Frontend build complete"
        MSG_CHECK_PREREQ="Checking prerequisites..."
        MSG_ALL_OK="All prerequisites are satisfied"
        MSG_SOME_MISSING="Some prerequisites are missing"
        MSG_DEV_START="Starting in development mode..."
        MSG_PREREQ_FAIL="Prerequisites not met. Run check first"
        MSG_CARGO_TAURI_DEV="Starting cargo tauri dev..."
        MSG_FLASK_AUTO="Flask server will be launched automatically by Tauri"
        MSG_QUIT_HINT="To quit: close the window or press Ctrl+C"
        MSG_RELEASE_START="Starting release build..."
        MSG_PREREQ_FAIL_SHORT="Prerequisites not met"
        MSG_CARGO_TAURI_BUILD="Running cargo tauri build (this may take a while)..."
        MSG_BUILD_DONE="Build complete!"
        MSG_ARTIFACTS="Artifacts:"
        MSG_UNKNOWN_CMD="Unknown command"
        MSG_USAGE="Usage: ./scripts/build-tauri.sh [build|bundle|dev|check|clean|help]"
        MSG_HELP_TITLE="YU AI Manager - Tauri Build"
        MSG_HELP_USAGE="Usage:"
        MSG_HELP_COMMANDS="Commands:"
        MSG_HELP_CMD_BUILD="Release build (default)"
        MSG_HELP_CMD_DEV="Development mode (hot reload)"
        MSG_HELP_CMD_CHECK="Prerequisites check only"
        MSG_HELP_EXAMPLES="Examples:"
        MSG_HELP_EX_CHECK="# Check prerequisites first"
        MSG_HELP_EX_BUILD="# Release build"
        MSG_HELP_EX_DEV="# Development mode"
        ;;
esac

# --- Prerequisites check ---
check_prerequisites() {
    local all_ok=0

    # Rust / cargo
    info "$MSG_CHECK_RUST"
    if command -v cargo &>/dev/null; then
        ok "rustc: $(rustc --version 2>&1)"
    else
        err "$MSG_CARGO_NOT_FOUND"
        all_ok=1
    fi

    # tauri-cli
    info "$MSG_CHECK_TAURI"
    if cargo tauri --version &>/dev/null; then
        ok "tauri-cli: $(cargo tauri --version 2>&1)"
    else
        warn "$MSG_TAURI_NOT_FOUND"
        all_ok=1
    fi

    # pnpm
    info "$MSG_CHECK_PNPM"
    if command -v pnpm &>/dev/null; then
        ok "pnpm: v$(pnpm --version 2>&1)"
    else
        warn "$MSG_PNPM_NOT_FOUND"
        if command -v npm &>/dev/null; then
            ok "npm: v$(npm --version 2>&1) (fallback)"
        else
            err "$MSG_NO_PKG_MGR"
            all_ok=1
        fi
    fi

    # Python environment: prefer uv, fallback to venv
    info "$MSG_CHECK_VENV"
    if command -v uv &>/dev/null; then
        if py_ver="$(uv run --no-sync python --version 2>&1)"; then
            ok "uv: $(uv --version 2>&1) / Python: $py_ver"
        else
            ok "uv: $(uv --version 2>&1)"
        fi
    elif [ -f "venv/bin/python" ]; then
        ok "Python: $(venv/bin/python --version 2>&1) (venv fallback)"
    elif [ -f "venv/Scripts/python.exe" ]; then
        ok "Python: $(venv/Scripts/python.exe --version 2>&1) (venv fallback)"
    elif [ -f ".venv/bin/python" ]; then
        ok "Python: $(.venv/bin/python --version 2>&1) (venv fallback)"
    elif [ -f ".venv/Scripts/python.exe" ]; then
        ok "Python: $(.venv/Scripts/python.exe --version 2>&1) (venv fallback)"
    else
        err "$MSG_VENV_NOT_FOUND"
        all_ok=1
    fi

    # src-tauri directory
    info "$MSG_CHECK_SRCTAURI"
    if [ -f "src-tauri/Cargo.toml" ]; then
        ok "src-tauri/Cargo.toml found"
    else
        err "$MSG_SRCTAURI_NOT_FOUND"
        all_ok=1
    fi

    # web_ui.py
    info "$MSG_CHECK_WEBUI"
    if [ -f "web_ui.py" ]; then
        ok "web_ui.py found"
    else
        err "$MSG_WEBUI_NOT_FOUND"
        all_ok=1
    fi

    return $all_ok
}

# --- Show built artifacts ---
show_artifacts() {
    local release_dir="src-tauri/target/release"
    [ -d "$release_dir" ] || return 0

    info "$MSG_ARTIFACTS"
    local found=0

    # Tauri 2 layout: target/release/{nsis,msi}
    # Tauri 1 layout: target/release/bundle/{nsis,msi,deb,appimage,dmg}
    local pairs=(
        "$release_dir/nsis:*.exe:NSIS"
        "$release_dir/msi:*.msi:MSI"
        "$release_dir/wix:*.msi:WiX"
        "$release_dir/bundle/nsis:*.exe:NSIS"
        "$release_dir/bundle/msi:*.msi:MSI"
        "$release_dir/bundle/deb:*.deb:DEB"
        "$release_dir/bundle/appimage:*.AppImage:AppImage"
        "$release_dir/bundle/dmg:*.dmg:DMG"
    )
    for pair in "${pairs[@]}"; do
        local d="${pair%%:*}"
        local rest="${pair#*:}"
        local pat="${rest%%:*}"
        local label="${rest#*:}"
        if [ -d "$d" ]; then
            while IFS= read -r f; do
                [ -n "$f" ] || continue
                echo "  $label: $f ($(du -h "$f" | cut -f1))"
                found=1
            done < <(find "$d" -name "$pat" 2>/dev/null)
        fi
    done

    if [ "$found" = "0" ]; then
        warn "(no installer artifacts found under $release_dir)"
    fi
}

# --- Clean build artifacts ---
do_clean() {
    local deep="${1:-0}"
    local targets=(
        "src-tauri/bundle"
        "src-tauri/bundle.zip"
        "src-tauri/target/release/bundle"
        "src-tauri/target/release/nsis"
        "src-tauri/target/release/msi"
        "src-tauri/target/release/wix"
        "src-tauri/target/release/resources"
    )
    for t in "${targets[@]}"; do
        if [ -e "$t" ]; then
            info "Removing $t"
            rm -rf "$t"
        fi
    done
    if [ "$deep" = "1" ]; then
        info "Deep clean: cargo clean (removes target/)"
        (cd src-tauri && cargo clean)
    fi
    ok "Clean complete"
}

# --- TypeScript frontend build ---
build_frontend() {
    info "$MSG_BUILD_FRONTEND"
    if command -v pnpm &>/dev/null; then
        pnpm run build
    else
        npm run build
    fi
    ok "$MSG_BUILD_FRONTEND_DONE"
}

# --- Main ---
echo ""
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  YU AI Manager - Tauri Build${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

case $COMMAND in
    check)
        info "$MSG_CHECK_PREREQ"
        if check_prerequisites; then
            echo ""
            ok "$MSG_ALL_OK"
        else
            echo ""
            err "$MSG_SOME_MISSING"
            exit 1
        fi
        ;;

    dev)
        info "$MSG_DEV_START"
        if ! check_prerequisites; then
            err "$MSG_PREREQ_FAIL"
            exit 1
        fi
        echo ""

        build_frontend
        echo ""

        info "$MSG_CARGO_TAURI_DEV"
        info "$MSG_FLASK_AUTO"
        info "$MSG_QUIT_HINT"
        echo ""
        cd src-tauri
        cargo tauri dev
        ;;

    build)
        info "$MSG_RELEASE_START"
        if ! check_prerequisites; then
            err "$MSG_PREREQ_FAIL_SHORT"
            exit 1
        fi
        echo ""

        build_frontend
        echo ""

        info "$MSG_CARGO_TAURI_BUILD"
        (cd src-tauri && cargo tauri build)

        echo ""
        ok "$MSG_BUILD_DONE"
        echo ""
        show_artifacts
        ;;

    bundle)
        info "Self-contained bundle build starting..."
        if ! check_prerequisites; then
            err "$MSG_PREREQ_FAIL_SHORT"
            exit 1
        fi
        echo ""

        build_frontend
        echo ""

        info "Staging bundle (Python embedded + dependencies + app files)..."
        if command -v uv &>/dev/null; then
            uv run python scripts/prepare-tauri-bundle.py --skip-ts-build
        elif [ -f "venv/bin/python" ]; then
            venv/bin/python scripts/prepare-tauri-bundle.py --skip-ts-build
        elif [ -f ".venv/bin/python" ]; then
            .venv/bin/python scripts/prepare-tauri-bundle.py --skip-ts-build
        else
            python3 scripts/prepare-tauri-bundle.py --skip-ts-build
        fi

        info "$MSG_CARGO_TAURI_BUILD"
        (cd src-tauri && cargo tauri build)

        echo ""
        ok "$MSG_BUILD_DONE"
        echo ""
        show_artifacts
        ;;

    clean)
        deep=0
        case "${2:-}" in
            --deep|--all|deep|all) deep=1 ;;
        esac
        do_clean "$deep"
        ;;

    help|--help|-h)
        cat << HELP

  $MSG_HELP_TITLE

  $MSG_HELP_USAGE
    ./scripts/build-tauri.sh [command]

  $MSG_HELP_COMMANDS
    build       $MSG_HELP_CMD_BUILD
    bundle      Self-contained build (Python embedded + deps + app)
    dev         $MSG_HELP_CMD_DEV
    check       $MSG_HELP_CMD_CHECK
    clean       Remove staged bundle/, bundle.zip, and target/release/{nsis,msi,bundle}
                (append --deep to also run cargo clean)

  $MSG_HELP_EXAMPLES
    ./scripts/build-tauri.sh check    $MSG_HELP_EX_CHECK
    ./scripts/build-tauri.sh          $MSG_HELP_EX_BUILD
    ./scripts/build-tauri.sh dev      $MSG_HELP_EX_DEV
    ./scripts/build-tauri.sh clean    # Clean stale build artifacts
    ./scripts/build-tauri.sh clean --deep   # Full clean incl. cargo target/

HELP
        ;;

    *)
        err "$MSG_UNKNOWN_CMD '$COMMAND'"
        echo "  $MSG_USAGE"
        exit 1
        ;;
esac

echo ""
