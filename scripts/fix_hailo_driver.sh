#!/usr/bin/env bash
# Rebuild and install the Hailo PCIe driver (hailo1x_pci) for the running kernel.
#
# Background:
#   - HailoRT 5.3.0 ships a prebuilt .ko targeting kernel 6.12.x only.
#   - On kernel 6.15+, del_timer_sync() was removed, replaced by
#     timer_delete_sync(), so even rebuilding fails without a small patch.
#   - This script applies the patch, rebuilds for the current kernel,
#     installs the new module, and reloads it.
#
# Usage:  sudo bash scripts/fix_hailo_driver.sh
#         LANG=en_US.UTF-8 sudo bash scripts/fix_hailo_driver.sh  (English)

set -euo pipefail

# ---------------------------------------------------------------------------
# i18n (ja default if LANG starts with "ja", otherwise en).
# ---------------------------------------------------------------------------
_lang="${LC_ALL:-${LANG:-en}}"
case "${_lang}" in
  ja*|JA*) LOCALE=ja ;;
  *)       LOCALE=en ;;
esac

msg() {
  local key="$1"
  case "${LOCALE}:${key}" in
    ja:kernel)          echo "==> カーネル: ${KVER}";;
    en:kernel)          echo "==> Kernel: ${KVER}";;
    ja:source)          echo "==> ソース: ${SRC_DIR}";;
    en:source)          echo "==> Source: ${SRC_DIR}";;
    ja:patching)        echo "==> monitor.c の del_timer_sync -> timer_delete_sync を置換中";;
    en:patching)        echo "==> Patching del_timer_sync -> timer_delete_sync in monitor.c";;
    ja:already_patched) echo "==> monitor.c はパッチ済み (del_timer_sync が無いためスキップ)";;
    en:already_patched) echo "==> monitor.c already patched (no del_timer_sync found), skip";;
    ja:building)        echo "==> モジュールをビルド中";;
    en:building)        echo "==> Building module";;
    ja:vermagic)        echo "==> ビルドした .ko の vermagic:";;
    en:vermagic)        echo "==> Built module vermagic:";;
    ja:backup)          echo "==> 既存 .ko を退避: ${TARGET_KO} -> ${TARGET_KO}.bak";;
    en:backup)          echo "==> Backing up existing module: ${TARGET_KO} -> ${TARGET_KO}.bak";;
    ja:installing)      echo "==> 新しい .ko をインストール中";;
    en:installing)      echo "==> Installing new module";;
    ja:modprobe)        echo "==> modprobe hailo1x_pci";;
    en:modprobe)        echo "==> modprobe hailo1x_pci";;
    ja:verify_lsmod)    echo "==> 確認: lsmod | grep hailo1x";;
    en:verify_lsmod)    echo "==> Verifying: lsmod | grep hailo1x";;
    ja:verify_dev)      echo "==> 確認: /dev/hailo1x-0";;
    en:verify_dev)      echo "==> Verifying: /dev/hailo1x-0";;
    ja:verify_dmesg)    echo "==> dmesg (hailo 関連の末尾):";;
    en:verify_dmesg)    echo "==> dmesg (last hailo lines):";;
    ja:done)            echo "==> 完了。yu_ai_manager を再起動して chat を試してください。";;
    en:done)            echo "==> Done. Restart yu_ai_manager and try the chat again.";;
    ja:build_failed)    echo "エラー: ビルド成果物 ${BUILT_KO} が生成されませんでした" >&2;;
    en:build_failed)    echo "ERROR: build did not produce ${BUILT_KO}" >&2;;
    ja:src_missing)     echo "エラー: ${SRC_DIR} が存在しません。hailort-pcie-driver パッケージをインストールしてください。" >&2;;
    en:src_missing)     echo "ERROR: ${SRC_DIR} not found. Install the hailort-pcie-driver package first." >&2;;
    ja:hdr_missing)     echo "エラー: ${KVER} 用の Linux ヘッダが見つかりません。" >&2;;
    en:hdr_missing)     echo "ERROR: Linux headers for kernel ${KVER} not found." >&2;;
    *)                  echo "[${key}]";;
  esac
}

KVER="$(uname -r)"
SRC_DIR="/usr/src/hailort-pcie-driver"
PCIE_DIR="${SRC_DIR}/linux/pcie"
MON_C="${SRC_DIR}/linux/vdma/monitor.c"
TARGET_KO="/lib/modules/${KVER}/kernel/drivers/misc/hailo1x_pci.ko"
BUILT_KO="${PCIE_DIR}/build/release/aarch64/hailo1x_pci.ko"
HDR_DIR="/lib/modules/${KVER}/build"

msg kernel
msg source

# Pre-flight checks ----------------------------------------------------------
if [[ ! -d "${SRC_DIR}" ]]; then msg src_missing; exit 1; fi
if [[ ! -d "${HDR_DIR}" ]]; then msg hdr_missing; exit 1; fi

# 1) Patch del_timer_sync (Linux 6.15+ removed it) ---------------------------
if grep -q '\bdel_timer_sync\b' "${MON_C}"; then
  msg patching
  sudo cp -n "${MON_C}" "${MON_C}.bak"
  sudo sed -i 's/\bdel_timer_sync\b/timer_delete_sync/g' "${MON_C}"
else
  msg already_patched
fi

# 2) Build -------------------------------------------------------------------
msg building
cd "${PCIE_DIR}"
sudo make clean
sudo make all

if [[ ! -f "${BUILT_KO}" ]]; then msg build_failed; exit 1; fi
msg vermagic
modinfo -F vermagic "${BUILT_KO}"

# 3) Install -----------------------------------------------------------------
if [[ -f "${TARGET_KO}" && ! -f "${TARGET_KO}.bak" ]]; then
  msg backup
  sudo mv "${TARGET_KO}" "${TARGET_KO}.bak"
fi
msg installing
sudo install -m 0644 "${BUILT_KO}" "${TARGET_KO}"
sudo depmod -a

# 4) Load --------------------------------------------------------------------
msg modprobe
sudo modprobe hailo1x_pci

# 5) Verify ------------------------------------------------------------------
msg verify_lsmod
lsmod | grep hailo1x || true
msg verify_dev
ls -la /dev/hailo1x-0 || true
msg verify_dmesg
sudo dmesg | grep -i hailo | tail -10 || true

msg done
