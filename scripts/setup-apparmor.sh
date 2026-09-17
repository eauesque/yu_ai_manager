#!/usr/bin/env bash
# ============================================================
# AppArmor setup script (Phase D)
#
# How to run:
#   sudo bash scripts/setup-apparmor.sh
#
# What it does:
#   1. Check AppArmor packages
#   2. Add lsm=apparmor to /boot/firmware/cmdline.txt (with backup)
#   3. Install NOPASSWD sudoers rule limited to apparmor_parser in /etc/sudoers.d/
#   4. Show reboot instructions
# ============================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

CMDLINE="/boot/firmware/cmdline.txt"
SUDOERS_FILE="/etc/sudoers.d/yu-ai-apparmor"

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
        MSG_ROOT_REQUIRED="このスクリプトは root で実行する必要があります:"
        MSG_TITLE="=== YU AI Manager: AppArmor セットアップ ==="
        MSG_STEP1="[1/4] AppArmor パッケージ... "
        MSG_PKG_OK="OK"
        MSG_PKG_NOT_INSTALLED="未インストール"
        MSG_PKG_INSTALLING="  インストール中..."
        MSG_PKG_DONE="  インストール完了"
        MSG_STEP2="[2/4] カーネルパラメータ (lsm=apparmor)... "
        MSG_ALREADY_ENABLED="有効化済み"
        MSG_CMDLINE_NOT_FOUND="${CMDLINE} が見つかりません"
        MSG_CMDLINE_MANUAL="  Raspberry Pi OS 以外の環境では、LSM パラメータを手動で設定してください"
        MSG_CMDLINE_GRUB="  GRUB: /etc/default/grub の GRUB_CMDLINE_LINUX に lsm=apparmor を追加"
        MSG_PARAM_ALREADY_SET="パラメータ設定済み (再起動後に有効化)"
        MSG_BACKUP="  バックアップ:"
        MSG_ADDED_LSM="  lsm=apparmor を追加しました"
        MSG_UPDATED="  更新後:"
        MSG_STEP3="[3/4] sudoers ルール (apparmor_parser NOPASSWD)... "
        MSG_SUDOERS_EXISTS="インストール済み"
        MSG_SUDOERS_INSTALLED="インストール完了"
        MSG_SUDOERS_USER="  対象ユーザー:"
        MSG_SUDOERS_CMD="  許可コマンド:"
        MSG_SUDOERS_SYNTAX_ERR="構文エラー"
        MSG_SUDOERS_REMOVED="  sudoers ファイルを削除しました。手動で設定してください"
        MSG_STEP4="[4/4] AppArmor サービス... "
        MSG_SVC_ENABLED="有効化済み"
        MSG_SETUP_COMPLETE="=== セットアップ完了 ==="
        MSG_ALREADY_RUNNING="AppArmor は既に動作中です。再起動は不要です。"
        MSG_ENABLE_CONFIG="config.json で OS 隔離を有効にしてください:"
        MSG_REBOOT_REQUIRED="再起動が必要です。"
        MSG_REBOOT_CMD="再起動コマンド:"
        MSG_AFTER_REBOOT="再起動後、config.json で OS 隔離を有効にしてください:"
        MSG_VERIFY="確認方法:"
        MSG_VERIFY_ENABLED="  cat /sys/module/apparmor/parameters/enabled  # Y なら有効"
        MSG_VERIFY_STATUS="  sudo aa-status                               # ロード済みプロファイル一覧"
        ;;
    ko)
        MSG_ROOT_REQUIRED="이 스크립트는 root로 실행해야 합니다:"
        MSG_TITLE="=== YU AI Manager: AppArmor 설정 ==="
        MSG_STEP1="[1/4] AppArmor 패키지... "
        MSG_PKG_OK="OK"
        MSG_PKG_NOT_INSTALLED="설치되지 않음"
        MSG_PKG_INSTALLING="  설치 중..."
        MSG_PKG_DONE="  설치 완료"
        MSG_STEP2="[2/4] 커널 매개변수 (lsm=apparmor)... "
        MSG_ALREADY_ENABLED="이미 활성화됨"
        MSG_CMDLINE_NOT_FOUND="${CMDLINE}을 찾을 수 없습니다"
        MSG_CMDLINE_MANUAL="  Raspberry Pi OS 이외의 환경에서는 LSM 매개변수를 수동으로 설정하세요"
        MSG_CMDLINE_GRUB="  GRUB: /etc/default/grub의 GRUB_CMDLINE_LINUX에 lsm=apparmor 추가"
        MSG_PARAM_ALREADY_SET="매개변수 설정됨 (재부팅 후 활성화)"
        MSG_BACKUP="  백업:"
        MSG_ADDED_LSM="  lsm=apparmor 추가됨"
        MSG_UPDATED="  업데이트됨:"
        MSG_STEP3="[3/4] sudoers 규칙 (apparmor_parser NOPASSWD)... "
        MSG_SUDOERS_EXISTS="이미 설치됨"
        MSG_SUDOERS_INSTALLED="설치 완료"
        MSG_SUDOERS_USER="  대상 사용자:"
        MSG_SUDOERS_CMD="  허용된 명령:"
        MSG_SUDOERS_SYNTAX_ERR="구문 오류"
        MSG_SUDOERS_REMOVED="  sudoers 파일을 삭제했습니다. 수동으로 설정하세요"
        MSG_STEP4="[4/4] AppArmor 서비스... "
        MSG_SVC_ENABLED="활성화됨"
        MSG_SETUP_COMPLETE="=== 설정 완료 ==="
        MSG_ALREADY_RUNNING="AppArmor가 이미 실행 중입니다. 재부팅이 필요하지 않습니다."
        MSG_ENABLE_CONFIG="config.json에서 OS 격리를 활성화하세요:"
        MSG_REBOOT_REQUIRED="재부팅이 필요합니다."
        MSG_REBOOT_CMD="재부팅 명령:"
        MSG_AFTER_REBOOT="재부팅 후 config.json에서 OS 격리를 활성화하세요:"
        MSG_VERIFY="확인 방법:"
        MSG_VERIFY_ENABLED="  cat /sys/module/apparmor/parameters/enabled  # Y이면 활성화"
        MSG_VERIFY_STATUS="  sudo aa-status                               # 로드된 프로필 목록"
        ;;
    zh_TW)
        MSG_ROOT_REQUIRED="此腳本必須以 root 身份執行："
        MSG_TITLE="=== YU AI Manager: AppArmor 設定 ==="
        MSG_STEP1="[1/4] AppArmor 套件... "
        MSG_PKG_OK="OK"
        MSG_PKG_NOT_INSTALLED="未安裝"
        MSG_PKG_INSTALLING="  安裝中..."
        MSG_PKG_DONE="  安裝完成"
        MSG_STEP2="[2/4] 核心參數 (lsm=apparmor)... "
        MSG_ALREADY_ENABLED="已啟用"
        MSG_CMDLINE_NOT_FOUND="找不到 ${CMDLINE}"
        MSG_CMDLINE_MANUAL="  非 Raspberry Pi OS 環境請手動設定 LSM 參數"
        MSG_CMDLINE_GRUB="  GRUB: 在 /etc/default/grub 的 GRUB_CMDLINE_LINUX 中加入 lsm=apparmor"
        MSG_PARAM_ALREADY_SET="參數已設定（重新開機後生效）"
        MSG_BACKUP="  備份："
        MSG_ADDED_LSM="  已加入 lsm=apparmor"
        MSG_UPDATED="  更新後："
        MSG_STEP3="[3/4] sudoers 規則 (apparmor_parser NOPASSWD)... "
        MSG_SUDOERS_EXISTS="已安裝"
        MSG_SUDOERS_INSTALLED="安裝完成"
        MSG_SUDOERS_USER="  目標使用者："
        MSG_SUDOERS_CMD="  允許的命令："
        MSG_SUDOERS_SYNTAX_ERR="語法錯誤"
        MSG_SUDOERS_REMOVED="  已刪除 sudoers 檔案。請手動設定"
        MSG_STEP4="[4/4] AppArmor 服務... "
        MSG_SVC_ENABLED="已啟用"
        MSG_SETUP_COMPLETE="=== 設定完成 ==="
        MSG_ALREADY_RUNNING="AppArmor 已在執行中。無需重新開機。"
        MSG_ENABLE_CONFIG="在 config.json 中啟用 OS 隔離："
        MSG_REBOOT_REQUIRED="需要重新開機。"
        MSG_REBOOT_CMD="重新開機指令："
        MSG_AFTER_REBOOT="重新開機後，在 config.json 中啟用 OS 隔離："
        MSG_VERIFY="驗證方式："
        MSG_VERIFY_ENABLED="  cat /sys/module/apparmor/parameters/enabled  # Y 表示已啟用"
        MSG_VERIFY_STATUS="  sudo aa-status                               # 列出已載入的設定檔"
        ;;
    zh_CN)
        MSG_ROOT_REQUIRED="此脚本必须以 root 身份运行："
        MSG_TITLE="=== YU AI Manager: AppArmor 设置 ==="
        MSG_STEP1="[1/4] AppArmor 软件包... "
        MSG_PKG_OK="OK"
        MSG_PKG_NOT_INSTALLED="未安装"
        MSG_PKG_INSTALLING="  安装中..."
        MSG_PKG_DONE="  安装完成"
        MSG_STEP2="[2/4] 内核参数 (lsm=apparmor)... "
        MSG_ALREADY_ENABLED="已启用"
        MSG_CMDLINE_NOT_FOUND="找不到 ${CMDLINE}"
        MSG_CMDLINE_MANUAL="  非 Raspberry Pi OS 环境请手动设置 LSM 参数"
        MSG_CMDLINE_GRUB="  GRUB: 在 /etc/default/grub 的 GRUB_CMDLINE_LINUX 中添加 lsm=apparmor"
        MSG_PARAM_ALREADY_SET="参数已设置（重启后生效）"
        MSG_BACKUP="  备份："
        MSG_ADDED_LSM="  已添加 lsm=apparmor"
        MSG_UPDATED="  更新后："
        MSG_STEP3="[3/4] sudoers 规则 (apparmor_parser NOPASSWD)... "
        MSG_SUDOERS_EXISTS="已安装"
        MSG_SUDOERS_INSTALLED="安装完成"
        MSG_SUDOERS_USER="  目标用户："
        MSG_SUDOERS_CMD="  允许的命令："
        MSG_SUDOERS_SYNTAX_ERR="语法错误"
        MSG_SUDOERS_REMOVED="  已删除 sudoers 文件。请手动配置"
        MSG_STEP4="[4/4] AppArmor 服务... "
        MSG_SVC_ENABLED="已启用"
        MSG_SETUP_COMPLETE="=== 设置完成 ==="
        MSG_ALREADY_RUNNING="AppArmor 已在运行中。无需重启。"
        MSG_ENABLE_CONFIG="在 config.json 中启用 OS 隔离："
        MSG_REBOOT_REQUIRED="需要重启。"
        MSG_REBOOT_CMD="重启命令："
        MSG_AFTER_REBOOT="重启后，在 config.json 中启用 OS 隔离："
        MSG_VERIFY="验证方式："
        MSG_VERIFY_ENABLED="  cat /sys/module/apparmor/parameters/enabled  # Y 表示已启用"
        MSG_VERIFY_STATUS="  sudo aa-status                               # 列出已加载的配置文件"
        ;;
    *)  # English (default)
        MSG_ROOT_REQUIRED="This script must be run as root:"
        MSG_TITLE="=== YU AI Manager: AppArmor Setup ==="
        MSG_STEP1="[1/4] AppArmor packages... "
        MSG_PKG_OK="OK"
        MSG_PKG_NOT_INSTALLED="not installed"
        MSG_PKG_INSTALLING="  Installing..."
        MSG_PKG_DONE="  Installation complete"
        MSG_STEP2="[2/4] Kernel parameters (lsm=apparmor)... "
        MSG_ALREADY_ENABLED="already enabled"
        MSG_CMDLINE_NOT_FOUND="${CMDLINE} not found"
        MSG_CMDLINE_MANUAL="  For non-Raspberry Pi OS environments, set the LSM parameter manually"
        MSG_CMDLINE_GRUB="  GRUB: add lsm=apparmor to GRUB_CMDLINE_LINUX in /etc/default/grub"
        MSG_PARAM_ALREADY_SET="parameter already set (will be active after reboot)"
        MSG_BACKUP="  Backup:"
        MSG_ADDED_LSM="  Added lsm=apparmor"
        MSG_UPDATED="  Updated:"
        MSG_STEP3="[3/4] sudoers rule (apparmor_parser NOPASSWD)... "
        MSG_SUDOERS_EXISTS="already installed"
        MSG_SUDOERS_INSTALLED="installed"
        MSG_SUDOERS_USER="  Target user:"
        MSG_SUDOERS_CMD="  Allowed command:"
        MSG_SUDOERS_SYNTAX_ERR="syntax error"
        MSG_SUDOERS_REMOVED="  Removed sudoers file. Please configure manually"
        MSG_STEP4="[4/4] AppArmor service... "
        MSG_SVC_ENABLED="enabled"
        MSG_SETUP_COMPLETE="=== Setup Complete ==="
        MSG_ALREADY_RUNNING="AppArmor is already running. No reboot required."
        MSG_ENABLE_CONFIG="Enable OS isolation in config.json:"
        MSG_REBOOT_REQUIRED="A reboot is required."
        MSG_REBOOT_CMD="Reboot with:"
        MSG_AFTER_REBOOT="After reboot, enable OS isolation in config.json:"
        MSG_VERIFY="Verification:"
        MSG_VERIFY_ENABLED="  cat /sys/module/apparmor/parameters/enabled  # Y means enabled"
        MSG_VERIFY_STATUS="  sudo aa-status                               # List loaded profiles"
        ;;
esac

# -- Check root --

if [ "$(id -u)" -ne 0 ]; then
    echo -e "${RED}${MSG_ROOT_REQUIRED}${NC}"
    echo "  sudo bash $0"
    exit 1
fi

echo -e "${CYAN}${MSG_TITLE}${NC}"
echo ""

# -- 1. Check packages --

echo -n "$MSG_STEP1"
if command -v aa-exec &>/dev/null && command -v apparmor_parser &>/dev/null; then
    echo -e "${GREEN}${MSG_PKG_OK}${NC}"
else
    echo -e "${YELLOW}${MSG_PKG_NOT_INSTALLED}${NC}"
    echo "$MSG_PKG_INSTALLING"
    apt-get update -qq && apt-get install -y -qq apparmor apparmor-utils
    echo -e "  ${GREEN}${MSG_PKG_DONE}${NC}"
fi

# -- 2. Check/add kernel parameters --

echo -n "$MSG_STEP2"

# Check current enabled state
KERNEL_ENABLED="N"
if [ -f /sys/module/apparmor/parameters/enabled ]; then
    KERNEL_ENABLED=$(cat /sys/module/apparmor/parameters/enabled)
fi

if [ "$KERNEL_ENABLED" = "Y" ]; then
    echo -e "${GREEN}${MSG_ALREADY_ENABLED}${NC}"
else
    if [ ! -f "$CMDLINE" ]; then
        echo -e "${RED}${MSG_CMDLINE_NOT_FOUND}${NC}"
        echo "$MSG_CMDLINE_MANUAL"
        echo "$MSG_CMDLINE_GRUB"
        exit 1
    fi

    CURRENT=$(cat "$CMDLINE")
    if echo "$CURRENT" | grep -q "lsm=apparmor"; then
        echo -e "${YELLOW}${MSG_PARAM_ALREADY_SET}${NC}"
    else
        # Backup
        BACKUP="${CMDLINE}.bak.$(date +%Y%m%d%H%M%S)"
        cp "$CMDLINE" "$BACKUP"
        echo ""
        echo "$MSG_BACKUP $BACKUP"

        # Append lsm=apparmor (cmdline.txt is a single line)
        echo "${CURRENT} lsm=apparmor" > "$CMDLINE"
        echo -e "  ${GREEN}${MSG_ADDED_LSM}${NC}"
        echo "$MSG_UPDATED $(cat "$CMDLINE")"
    fi
fi

# -- 3. Remove unsafe sudoers rule --

echo -n "$MSG_STEP3"

if [ -f "$SUDOERS_FILE" ]; then
    rm -f "$SUDOERS_FILE"
fi
echo -e "${YELLOW}NOPASSWD AppArmor profile loading is disabled.${NC}"

# -- 4. Enable AppArmor service --

echo -n "$MSG_STEP4"
if systemctl is-enabled apparmor &>/dev/null; then
    echo -e "${GREEN}${MSG_SVC_ENABLED}${NC}"
else
    systemctl enable apparmor
    echo -e "${GREEN}${MSG_SVC_ENABLED}${NC}"
fi

# -- Summary --

echo ""
echo -e "${CYAN}${MSG_SETUP_COMPLETE}${NC}"
echo ""

if [ "$KERNEL_ENABLED" = "Y" ]; then
    echo -e "${GREEN}${MSG_ALREADY_RUNNING}${NC}"
    echo ""
    echo "$MSG_ENABLE_CONFIG"
    echo '  "os_isolation": { "enabled": true, "linux": { "apparmor": true } }'
else
    echo -e "${YELLOW}${MSG_REBOOT_REQUIRED}${NC}"
    echo ""
    echo "$MSG_REBOOT_CMD"
    echo -e "  ${CYAN}sudo reboot${NC}"
    echo ""
    echo "$MSG_AFTER_REBOOT"
    echo '  "os_isolation": { "enabled": true, "linux": { "apparmor": true } }'
fi

echo ""
echo "$MSG_VERIFY"
echo "$MSG_VERIFY_ENABLED"
echo "$MSG_VERIFY_STATUS"
