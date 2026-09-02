#!/usr/bin/env bash
# YU AI Manager - Launcher (macOS / Linux)
set -e

# --- Detect locale ---
_LOCALE="${LC_ALL:-${LC_MESSAGES:-${LANG:-en_US.UTF-8}}}"
_LANG="${_LOCALE%%[._@]*}"  # e.g. "ja", "en", "ko", "zh"
_REGION="${_LOCALE#*.}"      # used for zh variants
case "$_LOCALE" in
    zh_TW*|zh_HK*|zh_Hant*) _LANG="zh_TW" ;;
    zh_CN*|zh_SG*|zh_Hans*) _LANG="zh_CN" ;;
esac

# --- i18n messages ---
case "$_LANG" in
    ja)
        MSG_PYTHON_NOT_FOUND="[ERROR] Python が見つかりません。"
        MSG_PYTHON_INSTALL="  以下から Python 3.11 以上をインストールしてください:"
        MSG_NODE_NOT_FOUND="[INFO] Node.js が見つかりません。"
        MSG_NODE_NEED="  フロントエンドのビルドには Node.js 22 LTS が必要です。"
        MSG_NODE_PROMPT="  ./bin/node/ にダウンロードしますか? (約 30 MB, 管理者権限不要) [Y/n]: "
        MSG_NODE_OPTIONAL="  Node.js がなくてもビルド済みファイルがあれば起動できます。"
        MSG_NODE_SKIP="  スキップしました。続行します..."
        MSG_NODE_FAIL="[WARNING] Node.js の自動インストールに失敗しました。続行します..."
        MSG_FFMPEG_NOT_FOUND="[INFO] ffmpeg が見つかりません。"
        MSG_FFMPEG_NEED="  動画分析・S2T・OCR 等の拡張機能で必要です (本体起動には不要)。"
        MSG_FFMPEG_PROMPT="  ./bin/ffmpeg/ にダウンロードしますか? (約 80 MB, 管理者権限不要) [Y/n]: "
        MSG_FFMPEG_SKIP="  スキップしました。動画系の拡張機能は無効になります。"
        MSG_FFMPEG_FAIL="[WARNING] ffmpeg の自動インストールに失敗しました。続行します..."
        MSG_ARGS_FOUND="[OK] launch-args.txt を検出"
        MSG_ARGS_NONE="[INFO] launch-args.txt なし (デフォルト設定で起動)"
        MSG_STARTING="サーバーを起動しています..."
        MSG_STOP_HINT="Ctrl+C で停止できます。"
        MSG_DIST_STALE="[INFO] Web UI バンドル (dist) が古いため再ビルドします..."
        MSG_DIST_BUILD_OK="[OK] ビルド完了。サーバーを再起動します..."
        MSG_DIST_BUILD_FAIL="[ERROR] pnpm run build に失敗しました。"
        MSG_DIST_NO_NODE="[ERROR] dist が古いですが Node.js がないため自動ビルドできません。YU_SKIP_DIST_CHECK=1 を付けて起動するとそのまま動かせます。"
        MSG_HAILO_NO_DKMS="[WARNING] Hailo ドライバが DKMS で管理されていません。カーネルアップデート後に /dev/hailo が消える場合があります。"
        MSG_HAILO_DKMS_FIX="  手動修正: sudo bash scripts/fix_hailo_dkms.sh"
        MSG_HAILO_FIX_PROMPT="  sudo があれば今すぐ修正できます。修正しますか? (y/N): "
        MSG_HAILO_FIX_OK="[OK] Hailo ドライバを DKMS で登録しました。"
        MSG_HAILO_FIX_FAIL="[WARNING] 修正に失敗しました。手動で実行してください: sudo bash scripts/fix_hailo_dkms.sh"
        MSG_HAILO_FIX_SKIP="  スキップしました。"
        ;;
    ko)
        MSG_PYTHON_NOT_FOUND="[ERROR] Python을 찾을 수 없습니다."
        MSG_PYTHON_INSTALL="  아래에서 Python 3.11 이상을 설치하세요:"
        MSG_NODE_NOT_FOUND="[INFO] Node.js를 찾을 수 없습니다."
        MSG_NODE_NEED="  프론트엔드 빌드에는 Node.js 22 LTS가 필요합니다."
        MSG_NODE_PROMPT="  ./bin/node/에 다운로드하시겠습니까? (약 30 MB, 관리자 권한 불필요) [Y/n]: "
        MSG_NODE_OPTIONAL="  Node.js가 없어도 빌드된 파일이 있으면 시작할 수 있습니다."
        MSG_NODE_SKIP="  건너뛰었습니다. 계속합니다..."
        MSG_NODE_FAIL="[WARNING] Node.js 자동 설치 실패. 계속합니다..."
        MSG_FFMPEG_NOT_FOUND="[INFO] ffmpeg를 찾을 수 없습니다。"
        MSG_FFMPEG_NEED="  동영상 분석/S2T/OCR 등 확장 기능에 필요 (본체 실행에는 불필요)."
        MSG_FFMPEG_PROMPT="  ./bin/ffmpeg/에 다운로드하시겠습니까? (약 80 MB, 관리자 권한 불필요) [Y/n]: "
        MSG_FFMPEG_SKIP="  건너뛰었습니다. 동영상 관련 확장 기능은 비활성화됩니다."
        MSG_FFMPEG_FAIL="[WARNING] ffmpeg 자동 설치 실패. 계속합니다..."
        MSG_ARGS_FOUND="[OK] launch-args.txt 감지됨"
        MSG_ARGS_NONE="[INFO] launch-args.txt 없음 (기본 설정으로 시작)"
        MSG_STARTING="서버를 시작하는 중..."
        MSG_STOP_HINT="Ctrl+C로 중지할 수 있습니다."
        MSG_DIST_STALE="[INFO] 웹 UI 번들(dist)이 오래되어 재빌드합니다..."
        MSG_DIST_BUILD_OK="[OK] 빌드 완료. 서버를 다시 시작합니다..."
        MSG_DIST_BUILD_FAIL="[ERROR] pnpm run build 실패."
        MSG_DIST_NO_NODE="[ERROR] dist가 오래되었지만 Node.js가 없어 자동 빌드할 수 없습니다. YU_SKIP_DIST_CHECK=1을 설정하면 그대로 실행할 수 있습니다."
        MSG_HAILO_NO_DKMS="[WARNING] Hailo 드라이버가 DKMS로 관리되지 않습니다. 커널 업데이트 후 /dev/hailo가 사라질 수 있습니다."
        MSG_HAILO_DKMS_FIX="  수동 수정: sudo bash scripts/fix_hailo_dkms.sh"
        MSG_HAILO_FIX_PROMPT="  sudo가 있으면 지금 바로 수정할 수 있습니다. 수정하시겠습니까? (y/N): "
        MSG_HAILO_FIX_OK="[OK] Hailo 드라이버를 DKMS로 등록했습니다."
        MSG_HAILO_FIX_FAIL="[WARNING] 수정에 실패했습니다. 수동으로 실행하세요: sudo bash scripts/fix_hailo_dkms.sh"
        MSG_HAILO_FIX_SKIP="  건너뛰었습니다."
        ;;
    zh_TW)
        MSG_PYTHON_NOT_FOUND="[ERROR] 找不到 Python。"
        MSG_PYTHON_INSTALL="  請從以下位置安裝 Python 3.11 以上版本："
        MSG_NODE_NOT_FOUND="[INFO] 找不到 Node.js。"
        MSG_NODE_NEED="  前端建置需要 Node.js 22 LTS。"
        MSG_NODE_PROMPT="  下載到 ./bin/node/ 嗎? (約 30 MB, 不需管理者權限) [Y/n]: "
        MSG_NODE_OPTIONAL="  沒有 Node.js 也可以使用已建置的檔案啟動。"
        MSG_NODE_SKIP="  已略過。繼續啟動..."
        MSG_NODE_FAIL="[WARNING] Node.js 自動安裝失敗。繼續啟動..."
        MSG_FFMPEG_NOT_FOUND="[INFO] 找不到 ffmpeg。"
        MSG_FFMPEG_NEED="  影片分析/S2T/OCR 等擴充功能需要 (主程式啟動不需要)。"
        MSG_FFMPEG_PROMPT="  下載到 ./bin/ffmpeg/ 嗎? (約 80 MB, 不需管理者權限) [Y/n]: "
        MSG_FFMPEG_SKIP="  已略過。影片相關擴充功能將停用。"
        MSG_FFMPEG_FAIL="[WARNING] ffmpeg 自動安裝失敗。繼續啟動..."
        MSG_ARGS_FOUND="[OK] 偵測到 launch-args.txt"
        MSG_ARGS_NONE="[INFO] 無 launch-args.txt（使用預設設定啟動）"
        MSG_STARTING="正在啟動伺服器..."
        MSG_STOP_HINT="按 Ctrl+C 可停止。"
        MSG_DIST_STALE="[INFO] Web UI bundle (dist) 已過時，正在重新建置..."
        MSG_DIST_BUILD_OK="[OK] 建置完成。正在重新啟動伺服器..."
        MSG_DIST_BUILD_FAIL="[ERROR] pnpm run build 失敗。"
        MSG_DIST_NO_NODE="[ERROR] dist 已過時，但找不到 Node.js 無法自動建置。設定 YU_SKIP_DIST_CHECK=1 可以照樣啟動。"
        MSG_HAILO_NO_DKMS="[WARNING] Hailo 驅動程式未由 DKMS 管理。核心更新後 /dev/hailo 可能消失。"
        MSG_HAILO_DKMS_FIX="  手動修正: sudo bash scripts/fix_hailo_dkms.sh"
        MSG_HAILO_FIX_PROMPT="  如有 sudo 權限，可立即修正。是否修正？ (y/N): "
        MSG_HAILO_FIX_OK="[OK] 已使用 DKMS 登錄 Hailo 驅動程式。"
        MSG_HAILO_FIX_FAIL="[WARNING] 修正失敗。請手動執行: sudo bash scripts/fix_hailo_dkms.sh"
        MSG_HAILO_FIX_SKIP="  已略過。"
        ;;
    zh_CN)
        MSG_PYTHON_NOT_FOUND="[ERROR] 找不到 Python。"
        MSG_PYTHON_INSTALL="  请从以下位置安装 Python 3.11 以上版本："
        MSG_NODE_NOT_FOUND="[INFO] 找不到 Node.js。"
        MSG_NODE_NEED="  前端构建需要 Node.js 22 LTS。"
        MSG_NODE_PROMPT="  下载到 ./bin/node/ 吗? (约 30 MB, 不需管理员权限) [Y/n]: "
        MSG_NODE_OPTIONAL="  没有 Node.js 也可以使用已构建的文件启动。"
        MSG_NODE_SKIP="  已跳过。继续启动..."
        MSG_NODE_FAIL="[WARNING] Node.js 自动安装失败。继续启动..."
        MSG_FFMPEG_NOT_FOUND="[INFO] 找不到 ffmpeg。"
        MSG_FFMPEG_NEED="  视频分析/S2T/OCR 等扩展功能需要 (主程序启动不需要)。"
        MSG_FFMPEG_PROMPT="  下载到 ./bin/ffmpeg/ 吗? (约 80 MB, 不需管理员权限) [Y/n]: "
        MSG_FFMPEG_SKIP="  已跳过。视频相关扩展功能将停用。"
        MSG_FFMPEG_FAIL="[WARNING] ffmpeg 自动安装失败。继续启动..."
        MSG_ARGS_FOUND="[OK] 检测到 launch-args.txt"
        MSG_ARGS_NONE="[INFO] 无 launch-args.txt（使用默认设置启动）"
        MSG_STARTING="正在启动服务器..."
        MSG_STOP_HINT="按 Ctrl+C 可停止。"
        MSG_DIST_STALE="[INFO] Web UI bundle (dist) 已过时，正在重新构建..."
        MSG_DIST_BUILD_OK="[OK] 构建完成。正在重启服务器..."
        MSG_DIST_BUILD_FAIL="[ERROR] pnpm run build 失败。"
        MSG_DIST_NO_NODE="[ERROR] dist 已过时，但未找到 Node.js 无法自动构建。设置 YU_SKIP_DIST_CHECK=1 可以照样启动。"
        MSG_HAILO_NO_DKMS="[WARNING] Hailo 驱动程序未由 DKMS 管理。内核更新后 /dev/hailo 可能消失。"
        MSG_HAILO_DKMS_FIX="  手动修复: sudo bash scripts/fix_hailo_dkms.sh"
        MSG_HAILO_FIX_PROMPT="  如有 sudo 权限，可立即修复。是否修复？ (y/N): "
        MSG_HAILO_FIX_OK="[OK] 已使用 DKMS 注册 Hailo 驱动程序。"
        MSG_HAILO_FIX_FAIL="[WARNING] 修复失败。请手动执行: sudo bash scripts/fix_hailo_dkms.sh"
        MSG_HAILO_FIX_SKIP="  已跳过。"
        ;;
    *)  # English (default)
        MSG_PYTHON_NOT_FOUND="[ERROR] Python not found."
        MSG_PYTHON_INSTALL="  Please install Python 3.11 or later from:"
        MSG_NODE_NOT_FOUND="[INFO] Node.js not found."
        MSG_NODE_NEED="  Node.js 22 LTS is required to build the frontend."
        MSG_NODE_PROMPT="  Download to ./bin/node/? (~30 MB, no admin needed) [Y/n]: "
        MSG_NODE_OPTIONAL="  You can still start if pre-built files exist."
        MSG_NODE_SKIP="  Skipped. Continuing..."
        MSG_NODE_FAIL="[WARNING] Node.js auto-install failed. Continuing..."
        MSG_FFMPEG_NOT_FOUND="[INFO] ffmpeg not found."
        MSG_FFMPEG_NEED="  Required by video/S2T/OCR extensions (the app itself starts without it)."
        MSG_FFMPEG_PROMPT="  Download to ./bin/ffmpeg/? (~80 MB, no admin needed) [Y/n]: "
        MSG_FFMPEG_SKIP="  Skipped. Video-related extensions will be disabled."
        MSG_FFMPEG_FAIL="[WARNING] ffmpeg auto-install failed. Continuing..."
        MSG_ARGS_FOUND="[OK] launch-args.txt detected"
        MSG_ARGS_NONE="[INFO] No launch-args.txt (using default settings)"
        MSG_STARTING="Starting server..."
        MSG_STOP_HINT="Press Ctrl+C to stop."
        MSG_DIST_STALE="[INFO] Web UI bundle (dist) is out of date — rebuilding..."
        MSG_DIST_BUILD_OK="[OK] Build complete — restarting server..."
        MSG_DIST_BUILD_FAIL="[ERROR] pnpm run build failed."
        MSG_DIST_NO_NODE="[ERROR] dist is stale but Node.js is not available; cannot auto-build. Set YU_SKIP_DIST_CHECK=1 to start anyway."
        MSG_HAILO_NO_DKMS="[WARNING] Hailo driver is not managed by DKMS. The driver (/dev/hailo) may disappear after a kernel update."
        MSG_HAILO_DKMS_FIX="  Manual fix: sudo bash scripts/fix_hailo_dkms.sh"
        MSG_HAILO_FIX_PROMPT="  If you have sudo, you can fix this now. Fix it? (y/N): "
        MSG_HAILO_FIX_OK="[OK] Hailo driver registered with DKMS."
        MSG_HAILO_FIX_FAIL="[WARNING] Fix failed. Run manually: sudo bash scripts/fix_hailo_dkms.sh"
        MSG_HAILO_FIX_SKIP="  Skipped."
        ;;
esac

echo "============================================"
echo "  YU AI Manager - Launcher"
echo "============================================"
echo

# --- uv bootstrap (project-scoped: ./bin/uv) ---
# We no longer support pip / system-python. uv handles Python install itself
# via `uv python install` (driven implicitly by `uv run`).
cd "$(dirname "$0")"

YU_SAFE_MODE=0
for arg in "$@"; do
    if [ "$arg" = "--safe-mode" ]; then
        YU_SAFE_MODE=1
    fi
done
if [ "$YU_SAFE_MODE" = "1" ]; then
    echo "[SAFE MODE] Passing --safe-mode to web_ui.py"
fi

UV_BIN="$(pwd)/bin/uv"
if [ ! -x "$UV_BIN" ]; then
    echo "[INFO] uv not found, downloading project-scoped binary..."
    if ! bash scripts/bootstrap_uv.sh; then
        echo "[ERROR] uv のダウンロードに失敗しました。ネットワーク接続を確認してください。"
        echo "        手動インストール: https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    fi
fi
UVVER=$("$UV_BIN" --version 2>&1)
echo "[OK] $UVVER"

"$UV_BIN" run --no-project --quiet python scripts/post_restart_apply.py || true

# --- Security audit (non-blocking, throttled to 24h) ---
# Detects known CVEs in Python (pip-audit) / Node (pnpm audit) deps. Default
# is notify-only; set YU_AUTO_SECURITY_PATCH=1 to apply patch-level bumps
# automatically. YU_SKIP_SECURITY_AUDIT=1 to disable entirely.
if [ "$YU_SAFE_MODE" = "1" ]; then
    echo "[SAFE MODE] Security audit skipped"
elif [ "${YU_SKIP_SECURITY_AUDIT:-0}" != "1" ]; then
    AUDIT_MODE="notify"
    if [ "${YU_AUTO_SECURITY_PATCH:-0}" = "1" ]; then
        AUDIT_MODE="apply"
    fi
    "$UV_BIN" run --no-project --quiet python scripts/security_audit.py --mode "$AUDIT_MODE" || true
fi

# --- onnxruntime variant selection ---
# .onnx_extra holds a cached choice (cpu/gpu/directml/rocm/silicon).
# On first launch we detect via scripts/detect_onnx_extra.py.
# To re-detect: rm .onnx_extra, or run `bin/uv run python scripts/install_onnx.py --force`.
ONNX_EXTRA=""
if [ "$YU_SAFE_MODE" = "1" ]; then
    ONNX_EXTRA="cpu"
elif [ -f ".onnx_extra" ]; then
    ONNX_EXTRA=$(tr -d '[:space:]' < .onnx_extra)
fi
if [ -z "$ONNX_EXTRA" ]; then
    ONNX_EXTRA=$("$UV_BIN" run --no-project --quiet python scripts/detect_onnx_extra.py 2>/dev/null | tr -d '[:space:]')
    [ -z "$ONNX_EXTRA" ] && ONNX_EXTRA="cpu"
    echo "$ONNX_EXTRA" > .onnx_extra
fi
echo "[OK] onnxruntime variant: $ONNX_EXTRA"
if [ "$YU_SAFE_MODE" != "1" ]; then
    "$UV_BIN" run --no-project --quiet python scripts/install_onnx.py --repair --variant "$ONNX_EXTRA" || exit $?
fi
LAUNCH_CMD="$UV_BIN run --extra $ONNX_EXTRA python"

# --- Hailo Python runtime (optional, Linux only) ---
# hailort wheel is not on PyPI and not declared in pyproject.toml because the
# build path is host-specific. install_hailo.py scans $HOME for a staged
# wheel and installs it idempotently; absent wheel is a silent no-op.
if [ "$YU_SAFE_MODE" = "1" ]; then
    echo "[SAFE MODE] Hailo runtime install skipped"
elif [ "$(uname -s)" = "Linux" ]; then
    "$UV_BIN" run --no-project --quiet python scripts/install_hailo.py || true
fi

# --- Hailo PCIe DKMS check (Linux only) ---
# hailort-pcie-driver installs via plain make install (no DKMS) by default.
# Without DKMS the kernel module must be rebuilt manually after every kernel
# update.  Warn the user when the package is present but the module for the
# running kernel is not registered in the DKMS tree.
if [ "$YU_SAFE_MODE" != "1" ] && [ "$(uname -s)" = "Linux" ]; then
    if dpkg -s hailort-pcie-driver &>/dev/null 2>&1; then
        _hailo_dkms_ok=0
        if command -v dkms &>/dev/null; then
            dkms status hailo1x_pci 2>/dev/null | grep -q "$(uname -r).*installed" && _hailo_dkms_ok=1
        fi
        if [ "$_hailo_dkms_ok" = "0" ]; then
            echo "$MSG_HAILO_NO_DKMS"
            _do_fix_hailo="n"
            if [ -t 0 ]; then
                printf "%s" "$MSG_HAILO_FIX_PROMPT"
                read -r _ans
                case "$_ans" in y|Y|yes|YES) _do_fix_hailo="y" ;; esac
            fi
            if [ "$_do_fix_hailo" = "y" ]; then
                if sudo bash "$(cd "$(dirname "$0")"; pwd)/scripts/fix_hailo_dkms.sh"; then
                    echo "$MSG_HAILO_FIX_OK"
                else
                    echo "$MSG_HAILO_FIX_FAIL"
                fi
            else
                echo "$MSG_HAILO_FIX_SKIP"
                echo "$MSG_HAILO_DKMS_FIX"
            fi
        fi
    fi
fi

# --- Node.js check (system → ./bin/node → consent prompt → bootstrap) ---
LOCAL_NODE_BIN="$(pwd)/bin/node/bin/node"
if [ -x "$LOCAL_NODE_BIN" ]; then
    # Project-scoped Node already present from a previous run.
    export PATH="$(pwd)/bin/node/bin:$PATH"
    NODEVER=$("$LOCAL_NODE_BIN" --version 2>&1)
    echo "[OK] Node.js $NODEVER (project-scoped)"
elif command -v node &>/dev/null; then
    NODEVER=$(node --version 2>&1)
    echo "[OK] Node.js $NODEVER"
elif [ "$YU_SAFE_MODE" = "1" ]; then
    echo "$MSG_NODE_SKIP"
    echo "$MSG_NODE_OPTIONAL"
else
    echo
    echo "$MSG_NODE_NOT_FOUND"
    echo "$MSG_NODE_NEED"
    echo
    # Auto-consent via env var (CI / non-interactive). Otherwise prompt.
    do_install_node="n"
    if [ "${YU_AUTO_INSTALL_NODE:-0}" = "1" ] || [ "${YU_AUTO_INSTALL:-0}" = "1" ]; then
        do_install_node="y"
        echo "[INFO] YU_AUTO_INSTALL_NODE=1 — auto-installing"
    elif [ -t 0 ]; then
        printf "%s" "$MSG_NODE_PROMPT"
        read -r ans
        case "$ans" in
            ""|y|Y|yes|YES) do_install_node="y" ;;
        esac
    else
        # Non-interactive without env var = skip silently.
        do_install_node="n"
    fi

    if [ "$do_install_node" = "y" ]; then
        if bash scripts/bootstrap_node.sh; then
            export PATH="$(pwd)/bin/node/bin:$PATH"
            NODEVER=$("$LOCAL_NODE_BIN" --version 2>&1)
            echo "[OK] Node.js $NODEVER (project-scoped)"
        else
            echo "$MSG_NODE_FAIL"
            echo "$MSG_NODE_OPTIONAL"
        fi
    else
        echo "$MSG_NODE_SKIP"
        echo "$MSG_NODE_OPTIONAL"
    fi
    echo
fi

# --- ffmpeg check (system → ./bin/ffmpeg → consent prompt → bootstrap) ---
LOCAL_FFMPEG_BIN="$(pwd)/bin/ffmpeg/ffmpeg"
if [ -x "$LOCAL_FFMPEG_BIN" ] && "$LOCAL_FFMPEG_BIN" -version >/dev/null 2>&1; then
    export PATH="$(pwd)/bin/ffmpeg:$PATH"
    FFVER=$("$LOCAL_FFMPEG_BIN" -version 2>&1 | head -n 1)
    echo "[OK] $FFVER (project-scoped)"
elif [ -x "$LOCAL_FFMPEG_BIN" ]; then
    # Binary exists but won't run (wrong arch, corrupt, etc.) — delete and re-download.
    echo "[INFO] project-scoped ffmpeg is not executable (wrong CPU arch?), removing..."
    rm -f "$LOCAL_FFMPEG_BIN" "$(dirname "$LOCAL_FFMPEG_BIN")/ffprobe"
    echo
    echo "$MSG_FFMPEG_NOT_FOUND"
    echo "$MSG_FFMPEG_NEED"
    echo
    do_install_ffmpeg="y"
    echo "[INFO] auto-triggering re-download to replace broken binary..."
    if bash scripts/bootstrap_ffmpeg.sh; then
        export PATH="$(pwd)/bin/ffmpeg:$PATH"
        FFVER=$("$LOCAL_FFMPEG_BIN" -version 2>&1 | head -n 1)
        echo "[OK] $FFVER (project-scoped)"
    else
        echo "$MSG_FFMPEG_FAIL"
    fi
elif command -v ffmpeg &>/dev/null; then
    FFVER=$(ffmpeg -version 2>&1 | head -n 1)
    echo "[OK] $FFVER"
elif [ "$YU_SAFE_MODE" = "1" ]; then
    echo "$MSG_FFMPEG_SKIP"
else
    echo
    echo "$MSG_FFMPEG_NOT_FOUND"
    echo "$MSG_FFMPEG_NEED"
    echo
    do_install_ffmpeg="n"
    if [ "${YU_AUTO_INSTALL_FFMPEG:-0}" = "1" ] || [ "${YU_AUTO_INSTALL:-0}" = "1" ]; then
        do_install_ffmpeg="y"
        echo "[INFO] YU_AUTO_INSTALL_FFMPEG=1 — auto-installing"
    elif [ -t 0 ]; then
        # On Linux, the bootstrap script prints distro hints rather than
        # downloading. Still gate behind a prompt so the hint isn't surprising.
        printf "%s" "$MSG_FFMPEG_PROMPT"
        read -r ans
        case "$ans" in
            ""|y|Y|yes|YES) do_install_ffmpeg="y" ;;
        esac
    fi

    if [ "$do_install_ffmpeg" = "y" ]; then
        set +e
        bash scripts/bootstrap_ffmpeg.sh
        rc=$?
        set -e
        if [ $rc -eq 0 ] && [ -x "$LOCAL_FFMPEG_BIN" ]; then
            export PATH="$(pwd)/bin/ffmpeg:$PATH"
            FFVER=$("$LOCAL_FFMPEG_BIN" -version 2>&1 | head -n 1)
            echo "[OK] $FFVER (project-scoped)"
        elif [ $rc -eq 2 ]; then
            # Linux: hint already printed by bootstrap script.
            :
        else
            echo "$MSG_FFMPEG_FAIL"
        fi
    else
        echo "$MSG_FFMPEG_SKIP"
    fi
    echo
fi

# --- launch-args.txt ---
if [ -f "launch-args.txt" ]; then
    echo "$MSG_ARGS_FOUND"
else
    echo "$MSG_ARGS_NONE"
fi

# --- Fast mode (Rust) ---
# fast_mode.py is the only judge. We ask and obey; we do not decide here.
# It prints one launch argument per line (not a space-joined command line)
# and exits 0 when the Rust server may be used: binary_path() lives under
# Path.cwd()/bin, and a real install can sit under a path containing spaces
# ("~/My Apps", "C:\Users\Taro Yamada") or shell glob characters. A
# space-joined line handed to an unquoted `$VAR` would IFS-split or glob-
# expand it into the wrong argv; reading one argument per line instead
# keeps each argument intact regardless of what it contains (short of a
# literal newline, which fast_mode.py refuses to emit for this reason --
# see tests/test_fast_mode_cli.py::test_resolve_falls_back_when_an_
# argument_contains_a_newline).
#
# stderr is left unredirected (not `2>/dev/null`) so decide()'s reason for
# declining fast mode reaches the user instead of vanishing silently.
YU_FAST_ARGS=()
YU_FAST_RC=1
# yu:fast-resolve:begin
_yu_resolve_fast_mode() {
    YU_FAST_ARGS=()
    YU_FAST_RC=1
    if [ "${YU_SKIP_FAST_MODE:-}" = "1" ]; then
        return 0
    fi
    YU_FAST_OUT="$(mktemp)"
    set +e
    "$UV_BIN" run --no-project --quiet python scripts/fast_mode.py \
        --resolve -- "$@" >"$YU_FAST_OUT"
    YU_FAST_RC=$?
    set -e
    if [ "$YU_FAST_RC" -eq 0 ]; then
        _yu_fast_first_line=1
        while IFS= read -r _yu_fast_line || [ -n "$_yu_fast_line" ]; do
            if [ "$_yu_fast_first_line" -eq 1 ]; then
                _yu_fast_first_line=0
                case "$_yu_fast_line" in
                    __YU_FAST_ENV_DB_KEY__=*)
                        YU_DB_KEY="${_yu_fast_line#__YU_FAST_ENV_DB_KEY__=}"
                        export YU_DB_KEY
                        continue
                        ;;
                esac
            fi
            YU_FAST_ARGS+=("$_yu_fast_line")
        done < "$YU_FAST_OUT"
    fi
    rm -f "$YU_FAST_OUT"
}
# yu:fast-resolve:end

_yu_resolve_fast_mode "$@"

# --- Launch ---
echo
echo "$MSG_STARTING"
echo "$MSG_STOP_HINT"
echo

# Launch loop: web_ui.py exits 75 (EX_TEMPFAIL) when the dist bundle is stale.
# Catch that, run `pnpm run build`, and re-launch once. Any other exit code is
# returned to the caller as-is. Bypass the whole thing with YU_SKIP_DIST_CHECK=1.
#
# The sentinels below are load-bearing: tests/test_start_sh_launch_loop.py
# extracts this exact region and runs it against stubs, so the ordering of the
# rebuild and the fast-mode re-resolve is checked against the real script
# rather than a copy of it.
# yu:launch-loop:begin
_yu_dist_retry=0
while :; do
    set +e
    if [ "$YU_FAST_RC" -eq 0 ] && [ "${#YU_FAST_ARGS[@]}" -gt 0 ]; then
        "${YU_FAST_ARGS[@]}"
        rc=$?
        if [ "$rc" -eq 127 ] || [ "$rc" -eq 126 ]; then
            # 127: exec could not find the command at all. 126: found but not
            # executable, or the executable's format is invalid (e.g. wrong
            # architecture) -- decide() already runs the binary once via
            # _read_compat_info before approving it, so this path is not
            # expected to be reachable in practice, but there is no reason to
            # leave a hole in the fallback net for it. Either way, fall back
            # to Python instead of leaving the user stuck; this is the
            # fallback of last resort for a fast-mode launch that cannot
            # actually run. Remember the failure so a later dist-retry
            # iteration of this same loop does not try the Rust binary again.
            echo "[fast-mode] Rust launch failed (exit $rc); falling back to Python." >&2
            YU_FAST_RC=1
            _yu_fast_launch_failed=1
            $LAUNCH_CMD web_ui.py "$@"
            rc=$?
        fi
    else
        $LAUNCH_CMD web_ui.py "$@"
        rc=$?
    fi
    set -e
    if [ "$rc" -ne 75 ]; then
        exit "$rc"
    fi
    if [ "$_yu_dist_retry" -ne 0 ]; then
        # Already rebuilt once and still got 75 — give up to avoid a loop.
        echo "[ERROR] dist still stale after rebuild." >&2
        exit "$rc"
    fi
    _yu_dist_retry=1
    if ! command -v pnpm >/dev/null 2>&1 && ! command -v npm >/dev/null 2>&1; then
        echo "$MSG_DIST_NO_NODE" >&2
        exit "$rc"
    fi
    if [ ! -d "node_modules/dictionary-en" ] && command -v pnpm >/dev/null 2>&1; then
        echo "[INFO] node_modules incomplete — running pnpm install..."
        CI=true pnpm install || true
    fi
    echo "$MSG_DIST_STALE"
    if command -v pnpm >/dev/null 2>&1; then
        if ! pnpm run build; then
            echo "$MSG_DIST_BUILD_FAIL" >&2
            exit "$rc"
        fi
    else
        if ! npm run build; then
            echo "$MSG_DIST_BUILD_FAIL" >&2
            exit "$rc"
        fi
    fi
    echo "$MSG_DIST_BUILD_OK"
    # The dist bundle was the reason fast mode was refused a moment ago
    # (decide() rejects a stale bundle and, because a binary cannot fix that,
    # skips acquisition entirely). Ask again now that it is fresh, or this
    # launch runs Python for no remaining reason and the recorded verdict
    # keeps naming a staleness that has already been fixed. Not after a Rust
    # binary that would not exec: re-resolving would hand back the same
    # unusable binary this loop just fell back from.
    if [ "${_yu_fast_launch_failed:-0}" -eq 0 ]; then
        _yu_resolve_fast_mode "$@"
    fi
done
# yu:launch-loop:end
