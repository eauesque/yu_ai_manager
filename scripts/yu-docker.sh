#!/bin/bash
# ==========================================
# YU AI Manager - Container management script
# Auto-detects Docker / Podman
# ==========================================
# Usage: ./scripts/yu-docker.sh [command]
# ==========================================

set -euo pipefail

# Move to project root (can be run from the scripts directory)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

COMMAND=${1:-help}

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
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
        MSG_ERR_PODMAN_COMPOSE="podman-compose または podman compose プラグインが必要です"
        MSG_ERR_NO_RUNTIME="docker または podman が必要です"
        MSG_INIT_RUNNING="初期セットアップを実行中..."
        MSG_INIT_DB_NOT_FOUND="data/tags.db が見つかりません"
        MSG_INIT_DB_HINT1="  tagdb_tool.py でスキャンして DB を作成するか、"
        MSG_INIT_DB_HINT2="  既存の tags.db を data/ にコピーしてください。"
        MSG_INIT_CONFIG_FOUND="data/config.json 検出"
        MSG_INIT_CONFIG_COPIED="config.json.example -> data/config.json にコピーしました"
        MSG_INIT_CONFIG_MISSING="config.json が見つかりません (なくても起動可能)"
        MSG_INIT_DONE="セットアップ完了"
        MSG_BUILD="イメージをビルド中"
        MSG_BUILD_DONE="ビルド完了"
        MSG_UP="本番コンテナを起動中 (ポート 5000)..."
        MSG_UP_ACCESS="アクセス: http://localhost:5000"
        MSG_DEV="開発コンテナを起動中 (ポート 5001)..."
        MSG_DEV_ACCESS="アクセス: http://localhost:5001"
        MSG_DOWN="コンテナを停止中..."
        MSG_DOWN_DONE="停止しました"
        MSG_RESTART="再起動中..."
        MSG_RESTART_DONE="再起動完了"
        MSG_LOGS="ログを表示中 (Ctrl+C で終了)..."
        MSG_TEST="テストを実行中..."
        MSG_SHELL="コンテナのシェルに接続中"
        MSG_DBINFO="データベース情報..."
        MSG_DBINFO_NOT_FOUND="data/tags.db が見つかりません"
        MSG_CLEAN_WARN="全てのコンテナとイメージを削除します"
        MSG_CLEAN_CONFIRM="続行しますか? (y/N): "
        MSG_CLEAN_DONE="削除完了"
        MSG_CLEAN_CANCEL="キャンセルしました"
        MSG_UNKNOWN_CMD="不明なコマンド"
        MSG_HELP_TITLE="YU AI Manager - コンテナ管理 (Docker / Podman)"
        MSG_HELP_USAGE="使い方:"
        MSG_HELP_COMMANDS="コマンド:"
        MSG_HELP_CMD_BUILD="イメージをビルド"
        MSG_HELP_CMD_UP="本番コンテナを起動 (ポート 5000)"
        MSG_HELP_CMD_DEV="開発モードで起動 (ポート 5001, ホットリロード)"
        MSG_HELP_CMD_DOWN="コンテナを停止"
        MSG_HELP_CMD_RESTART="コンテナを再起動"
        MSG_HELP_CMD_LOGS="ログを表示 (Ctrl+C で終了)"
        MSG_HELP_CMD_PS="コンテナの状態を表示"
        MSG_HELP_CMD_TEST="テストを実行"
        MSG_HELP_CMD_SHELL="コンテナのシェルに接続"
        MSG_HELP_CMD_DBINFO="データベース情報を表示"
        MSG_HELP_CMD_CLEAN="全て削除 (イメージ含む)"
        MSG_HELP_CMD_INIT="初期セットアップ (data/uploads 作成)"
        MSG_HELP_EXAMPLES="例:"
        MSG_HELP_EX_INIT="# 初回のみ"
        ;;
    ko)
        MSG_ERR_PODMAN_COMPOSE="podman-compose 또는 podman compose 플러그인이 필요합니다"
        MSG_ERR_NO_RUNTIME="docker 또는 podman이 필요합니다"
        MSG_INIT_RUNNING="초기 설정 실행 중..."
        MSG_INIT_DB_NOT_FOUND="data/tags.db를 찾을 수 없습니다"
        MSG_INIT_DB_HINT1="  tagdb_tool.py로 스캔하여 DB를 생성하거나,"
        MSG_INIT_DB_HINT2="  기존 tags.db를 data/에 복사하세요."
        MSG_INIT_CONFIG_FOUND="data/config.json 감지됨"
        MSG_INIT_CONFIG_COPIED="config.json.example -> data/config.json 복사 완료"
        MSG_INIT_CONFIG_MISSING="config.json을 찾을 수 없습니다 (없어도 실행 가능)"
        MSG_INIT_DONE="설정 완료"
        MSG_BUILD="이미지 빌드 중"
        MSG_BUILD_DONE="빌드 완료"
        MSG_UP="프로덕션 컨테이너 시작 중 (포트 5000)..."
        MSG_UP_ACCESS="접속: http://localhost:5000"
        MSG_DEV="개발 컨테이너 시작 중 (포트 5001)..."
        MSG_DEV_ACCESS="접속: http://localhost:5001"
        MSG_DOWN="컨테이너 중지 중..."
        MSG_DOWN_DONE="중지됨"
        MSG_RESTART="재시작 중..."
        MSG_RESTART_DONE="재시작 완료"
        MSG_LOGS="로그 표시 중 (Ctrl+C로 종료)..."
        MSG_TEST="테스트 실행 중..."
        MSG_SHELL="컨테이너 셸에 접속 중"
        MSG_DBINFO="데이터베이스 정보..."
        MSG_DBINFO_NOT_FOUND="data/tags.db를 찾을 수 없습니다"
        MSG_CLEAN_WARN="모든 컨테이너와 이미지를 삭제합니다"
        MSG_CLEAN_CONFIRM="계속하시겠습니까? (y/N): "
        MSG_CLEAN_DONE="삭제 완료"
        MSG_CLEAN_CANCEL="취소되었습니다"
        MSG_UNKNOWN_CMD="알 수 없는 명령"
        MSG_HELP_TITLE="YU AI Manager - 컨테이너 관리 (Docker / Podman)"
        MSG_HELP_USAGE="사용법:"
        MSG_HELP_COMMANDS="명령어:"
        MSG_HELP_CMD_BUILD="이미지 빌드"
        MSG_HELP_CMD_UP="프로덕션 컨테이너 시작 (포트 5000)"
        MSG_HELP_CMD_DEV="개발 모드로 시작 (포트 5001, 핫 리로드)"
        MSG_HELP_CMD_DOWN="컨테이너 중지"
        MSG_HELP_CMD_RESTART="컨테이너 재시작"
        MSG_HELP_CMD_LOGS="로그 표시 (Ctrl+C로 종료)"
        MSG_HELP_CMD_PS="컨테이너 상태 표시"
        MSG_HELP_CMD_TEST="테스트 실행"
        MSG_HELP_CMD_SHELL="컨테이너 셸에 접속"
        MSG_HELP_CMD_DBINFO="데이터베이스 정보 표시"
        MSG_HELP_CMD_CLEAN="모두 삭제 (이미지 포함)"
        MSG_HELP_CMD_INIT="초기 설정 (data/uploads 생성)"
        MSG_HELP_EXAMPLES="예시:"
        MSG_HELP_EX_INIT="# 처음 한 번만"
        ;;
    zh_TW)
        MSG_ERR_PODMAN_COMPOSE="需要 podman-compose 或 podman compose 外掛"
        MSG_ERR_NO_RUNTIME="需要 docker 或 podman"
        MSG_INIT_RUNNING="正在執行初始設定..."
        MSG_INIT_DB_NOT_FOUND="找不到 data/tags.db"
        MSG_INIT_DB_HINT1="  使用 tagdb_tool.py 掃描建立 DB，"
        MSG_INIT_DB_HINT2="  或將現有的 tags.db 複製到 data/。"
        MSG_INIT_CONFIG_FOUND="偵測到 data/config.json"
        MSG_INIT_CONFIG_COPIED="已複製 config.json.example -> data/config.json"
        MSG_INIT_CONFIG_MISSING="找不到 config.json（沒有也可以啟動）"
        MSG_INIT_DONE="設定完成"
        MSG_BUILD="正在建置映像檔"
        MSG_BUILD_DONE="建置完成"
        MSG_UP="正在啟動正式環境容器（連接埠 5000）..."
        MSG_UP_ACCESS="存取: http://localhost:5000"
        MSG_DEV="正在啟動開發環境容器（連接埠 5001）..."
        MSG_DEV_ACCESS="存取: http://localhost:5001"
        MSG_DOWN="正在停止容器..."
        MSG_DOWN_DONE="已停止"
        MSG_RESTART="正在重新啟動..."
        MSG_RESTART_DONE="重新啟動完成"
        MSG_LOGS="正在顯示日誌（Ctrl+C 退出）..."
        MSG_TEST="正在執行測試..."
        MSG_SHELL="正在連線到容器 shell"
        MSG_DBINFO="資料庫資訊..."
        MSG_DBINFO_NOT_FOUND="找不到 data/tags.db"
        MSG_CLEAN_WARN="將刪除所有容器和映像檔"
        MSG_CLEAN_CONFIRM="是否繼續？(y/N): "
        MSG_CLEAN_DONE="刪除完成"
        MSG_CLEAN_CANCEL="已取消"
        MSG_UNKNOWN_CMD="未知的命令"
        MSG_HELP_TITLE="YU AI Manager - 容器管理 (Docker / Podman)"
        MSG_HELP_USAGE="用法："
        MSG_HELP_COMMANDS="命令："
        MSG_HELP_CMD_BUILD="建置映像檔"
        MSG_HELP_CMD_UP="啟動正式環境容器（連接埠 5000）"
        MSG_HELP_CMD_DEV="啟動開發模式（連接埠 5001，熱重載）"
        MSG_HELP_CMD_DOWN="停止容器"
        MSG_HELP_CMD_RESTART="重新啟動容器"
        MSG_HELP_CMD_LOGS="顯示日誌（Ctrl+C 退出）"
        MSG_HELP_CMD_PS="顯示容器狀態"
        MSG_HELP_CMD_TEST="執行測試"
        MSG_HELP_CMD_SHELL="連線到容器 shell"
        MSG_HELP_CMD_DBINFO="顯示資料庫資訊"
        MSG_HELP_CMD_CLEAN="刪除所有（含映像檔）"
        MSG_HELP_CMD_INIT="初始設定（建立 data/uploads）"
        MSG_HELP_EXAMPLES="範例："
        MSG_HELP_EX_INIT="# 僅首次需要"
        ;;
    zh_CN)
        MSG_ERR_PODMAN_COMPOSE="需要 podman-compose 或 podman compose 插件"
        MSG_ERR_NO_RUNTIME="需要 docker 或 podman"
        MSG_INIT_RUNNING="正在执行初始设置..."
        MSG_INIT_DB_NOT_FOUND="找不到 data/tags.db"
        MSG_INIT_DB_HINT1="  使用 tagdb_tool.py 扫描创建 DB，"
        MSG_INIT_DB_HINT2="  或将现有的 tags.db 复制到 data/。"
        MSG_INIT_CONFIG_FOUND="检测到 data/config.json"
        MSG_INIT_CONFIG_COPIED="已复制 config.json.example -> data/config.json"
        MSG_INIT_CONFIG_MISSING="找不到 config.json（没有也可以启动）"
        MSG_INIT_DONE="设置完成"
        MSG_BUILD="正在构建镜像"
        MSG_BUILD_DONE="构建完成"
        MSG_UP="正在启动生产容器（端口 5000）..."
        MSG_UP_ACCESS="访问: http://localhost:5000"
        MSG_DEV="正在启动开发容器（端口 5001）..."
        MSG_DEV_ACCESS="访问: http://localhost:5001"
        MSG_DOWN="正在停止容器..."
        MSG_DOWN_DONE="已停止"
        MSG_RESTART="正在重启..."
        MSG_RESTART_DONE="重启完成"
        MSG_LOGS="正在显示日志（Ctrl+C 退出）..."
        MSG_TEST="正在运行测试..."
        MSG_SHELL="正在连接到容器 shell"
        MSG_DBINFO="数据库信息..."
        MSG_DBINFO_NOT_FOUND="找不到 data/tags.db"
        MSG_CLEAN_WARN="将删除所有容器和镜像"
        MSG_CLEAN_CONFIRM="是否继续？(y/N): "
        MSG_CLEAN_DONE="删除完成"
        MSG_CLEAN_CANCEL="已取消"
        MSG_UNKNOWN_CMD="未知的命令"
        MSG_HELP_TITLE="YU AI Manager - 容器管理 (Docker / Podman)"
        MSG_HELP_USAGE="用法："
        MSG_HELP_COMMANDS="命令："
        MSG_HELP_CMD_BUILD="构建镜像"
        MSG_HELP_CMD_UP="启动生产容器（端口 5000）"
        MSG_HELP_CMD_DEV="启动开发模式（端口 5001，热重载）"
        MSG_HELP_CMD_DOWN="停止容器"
        MSG_HELP_CMD_RESTART="重启容器"
        MSG_HELP_CMD_LOGS="显示日志（Ctrl+C 退出）"
        MSG_HELP_CMD_PS="显示容器状态"
        MSG_HELP_CMD_TEST="运行测试"
        MSG_HELP_CMD_SHELL="连接到容器 shell"
        MSG_HELP_CMD_DBINFO="显示数据库信息"
        MSG_HELP_CMD_CLEAN="删除所有（含镜像）"
        MSG_HELP_CMD_INIT="初始设置（创建 data/uploads）"
        MSG_HELP_EXAMPLES="示例："
        MSG_HELP_EX_INIT="# 仅首次需要"
        ;;
    *)  # English (default)
        MSG_ERR_PODMAN_COMPOSE="podman-compose or the podman compose plugin is required"
        MSG_ERR_NO_RUNTIME="docker or podman is required"
        MSG_INIT_RUNNING="Running initial setup..."
        MSG_INIT_DB_NOT_FOUND="data/tags.db not found"
        MSG_INIT_DB_HINT1="  Create a DB by scanning with tagdb_tool.py,"
        MSG_INIT_DB_HINT2="  or copy an existing tags.db to data/."
        MSG_INIT_CONFIG_FOUND="data/config.json found"
        MSG_INIT_CONFIG_COPIED="Copied config.json.example -> data/config.json"
        MSG_INIT_CONFIG_MISSING="config.json not found (application can run without it)"
        MSG_INIT_DONE="Setup complete"
        MSG_BUILD="Building image"
        MSG_BUILD_DONE="Build complete"
        MSG_UP="Starting production container (port 5000)..."
        MSG_UP_ACCESS="Access: http://localhost:5000"
        MSG_DEV="Starting development container (port 5001)..."
        MSG_DEV_ACCESS="Access: http://localhost:5001"
        MSG_DOWN="Stopping containers..."
        MSG_DOWN_DONE="Stopped"
        MSG_RESTART="Restarting..."
        MSG_RESTART_DONE="Restart complete"
        MSG_LOGS="Showing logs (Ctrl+C to exit)..."
        MSG_TEST="Running tests..."
        MSG_SHELL="Accessing shell in container"
        MSG_DBINFO="Database information..."
        MSG_DBINFO_NOT_FOUND="data/tags.db not found"
        MSG_CLEAN_WARN="This will remove all containers and images"
        MSG_CLEAN_CONFIRM="Continue? (y/N): "
        MSG_CLEAN_DONE="Removal complete"
        MSG_CLEAN_CANCEL="Cancelled"
        MSG_UNKNOWN_CMD="Unknown command"
        MSG_HELP_TITLE="YU AI Manager - Container Management (Docker / Podman)"
        MSG_HELP_USAGE="Usage:"
        MSG_HELP_COMMANDS="Commands:"
        MSG_HELP_CMD_BUILD="Build image"
        MSG_HELP_CMD_UP="Start production container (port 5000)"
        MSG_HELP_CMD_DEV="Start development mode (port 5001, hot-reload)"
        MSG_HELP_CMD_DOWN="Stop containers"
        MSG_HELP_CMD_RESTART="Restart containers"
        MSG_HELP_CMD_LOGS="Show logs (Ctrl+C to exit)"
        MSG_HELP_CMD_PS="Show container status"
        MSG_HELP_CMD_TEST="Run tests"
        MSG_HELP_CMD_SHELL="Access container shell"
        MSG_HELP_CMD_DBINFO="Show database information"
        MSG_HELP_CMD_CLEAN="Remove everything (including images)"
        MSG_HELP_CMD_INIT="Initial setup (create data/uploads)"
        MSG_HELP_EXAMPLES="Examples:"
        MSG_HELP_EX_INIT="# first time only"
        ;;
esac

# Auto-detect container runtime (docker / podman)
if command -v docker &>/dev/null; then
    RUNTIME=docker
    COMPOSE="docker compose"
elif command -v podman &>/dev/null; then
    RUNTIME=podman
    # Detect podman-compose (pip) or podman compose (plugin)
    if podman compose version &>/dev/null 2>&1; then
        COMPOSE="podman compose"
    elif command -v podman-compose &>/dev/null; then
        COMPOSE="podman-compose"
    else
        echo "Error: $MSG_ERR_PODMAN_COMPOSE" >&2
        exit 1
    fi
else
    echo "Error: $MSG_ERR_NO_RUNTIME" >&2
    exit 1
fi

show_help() {
    cat << HELP

  $MSG_HELP_TITLE

  $MSG_HELP_USAGE
    ./scripts/yu-docker.sh [command]

  $MSG_HELP_COMMANDS
    build       $MSG_HELP_CMD_BUILD
    up          $MSG_HELP_CMD_UP
    dev         $MSG_HELP_CMD_DEV
    down        $MSG_HELP_CMD_DOWN
    restart     $MSG_HELP_CMD_RESTART
    logs        $MSG_HELP_CMD_LOGS
    ps          $MSG_HELP_CMD_PS
    test        $MSG_HELP_CMD_TEST
    shell       $MSG_HELP_CMD_SHELL
    db-info     $MSG_HELP_CMD_DBINFO
    clean       $MSG_HELP_CMD_CLEAN
    init        $MSG_HELP_CMD_INIT

  $MSG_HELP_EXAMPLES
    ./scripts/yu-docker.sh init     $MSG_HELP_EX_INIT
    ./scripts/yu-docker.sh build
    ./scripts/yu-docker.sh up
    ./scripts/yu-docker.sh logs

HELP
}

# Initial setup
do_init() {
    info "$MSG_INIT_RUNNING"
    mkdir -p data uploads

    if [ ! -f "data/tags.db" ]; then
        warn "$MSG_INIT_DB_NOT_FOUND"
        echo "$MSG_INIT_DB_HINT1"
        echo "$MSG_INIT_DB_HINT2"
    else
        ok "data/tags.db found ($(du -h data/tags.db | cut -f1))"
    fi

    if [ -f "data/config.json" ]; then
        ok "$MSG_INIT_CONFIG_FOUND"
    else
        if [ -f "config.json.example" ]; then
            cp config.json.example data/config.json
            ok "$MSG_INIT_CONFIG_COPIED"
        else
            warn "$MSG_INIT_CONFIG_MISSING"
        fi
    fi

    ok "$MSG_INIT_DONE"
}

case $COMMAND in
    build)
        info "$MSG_BUILD ($RUNTIME)..."
        $COMPOSE build
        ok "$MSG_BUILD_DONE"
        ;;
    up)
        info "$MSG_UP"
        $COMPOSE up yu-ai-manager -d
        echo ""
        $COMPOSE ps
        echo ""
        ok "$MSG_UP_ACCESS"
        ;;
    dev)
        info "$MSG_DEV"
        $COMPOSE up yu-ai-manager-dev -d
        echo ""
        $COMPOSE ps
        echo ""
        ok "$MSG_DEV_ACCESS"
        ;;
    down)
        info "$MSG_DOWN"
        $COMPOSE down
        ok "$MSG_DOWN_DONE"
        ;;
    restart)
        info "$MSG_RESTART"
        $COMPOSE restart
        echo ""
        $COMPOSE ps
        ok "$MSG_RESTART_DONE"
        ;;
    logs)
        info "$MSG_LOGS"
        $COMPOSE logs -f --tail=100
        ;;
    ps)
        $COMPOSE ps -a
        ;;
    test)
        info "$MSG_TEST"
        $COMPOSE run --rm test
        ;;
    shell)
        TARGET=${2:-yu-ai-manager}
        info "$MSG_SHELL ${TARGET}..."
        $COMPOSE exec "$TARGET" bash || $COMPOSE run --rm yu-ai-manager bash
        ;;
    db-info)
        info "$MSG_DBINFO"
        if [ -f "data/tags.db" ]; then
            $COMPOSE run --rm yu-ai-manager \
                python -c "
import sqlite3
conn = sqlite3.connect('/app/data/tags.db')
cur = conn.cursor()
tables = cur.execute('SELECT name FROM sqlite_master WHERE type=\"table\"').fetchall()
for t in tables:
    name = t[0]
    count = cur.execute(f'SELECT COUNT(*) FROM [{name}]').fetchone()[0]
    print(f'  {name}: {count} rows')
conn.close()
"
        else
            err "$MSG_DBINFO_NOT_FOUND"
        fi
        ;;
    clean)
        warn "$MSG_CLEAN_WARN"
        read -p "$MSG_CLEAN_CONFIRM" -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            $COMPOSE down -v --rmi all 2>/dev/null || true
            ok "$MSG_CLEAN_DONE"
        else
            info "$MSG_CLEAN_CANCEL"
        fi
        ;;
    init)
        do_init
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        err "$MSG_UNKNOWN_CMD '$COMMAND'"
        show_help
        exit 1
        ;;
esac
