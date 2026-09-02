#!/usr/bin/env bash
# Fix Hailo PCIe driver by registering it with DKMS.
# Must be run as root (called via: sudo bash scripts/fix_hailo_dkms.sh).
set -euo pipefail

if [ "$(id -u)" != "0" ]; then
    echo "[ERROR] このスクリプトは root (sudo) で実行してください。" >&2
    echo "[ERROR] Run as root: sudo bash scripts/fix_hailo_dkms.sh" >&2
    exit 1
fi

PCIE_DIR='/usr/src/hailort-pcie-driver/linux/pcie'

if [ ! -d "$PCIE_DIR" ]; then
    echo "[ERROR] $PCIE_DIR が見つかりません。hailort-pcie-driver がインストールされていません。" >&2
    exit 1
fi

echo "[INFO] 現カーネル: $(uname -r)"

# Remove stale DKMS entry if present (ignore errors — may not exist)
dkms remove hailo1x_pci/5.3.0 --all 2>/dev/null || true

echo "[INFO] make install_dkms を実行中..."
cd "$PCIE_DIR"
if ! make install_dkms 2>&1; then
    echo "[ERROR] make install_dkms に失敗しました。" >&2
    exit 1
fi

echo "[INFO] モジュールをロード中..."
modprobe -rq hailo1x_pci 2>/dev/null || true
if ! modprobe hailo1x_pci; then
    echo "[ERROR] modprobe hailo1x_pci に失敗しました。" >&2
    exit 1
fi

udevadm control --reload-rules
udevadm trigger

# Verify: DKMS registration is the primary success criterion.
# Device node presence is informational — hardware may not be connected.
if dkms status hailo1x_pci 2>/dev/null | grep -q "$(uname -r).*installed"; then
    echo "[OK] Hailo ドライバを DKMS で登録しました (カーネル: $(uname -r))"
    echo "[OK] 次回以降のカーネルアップデート時は自動で再ビルドされます。"
else
    echo "[ERROR] DKMS への登録を確認できませんでした。" >&2
    dkms status hailo1x_pci 2>/dev/null >&2 || true
    exit 1
fi

# Device node presence: informational only
if ls /dev/hailo* &>/dev/null 2>&1; then
    echo "[INFO] デバイスノード確認: $(ls /dev/hailo*)"
else
    echo "[INFO] /dev/hailo* は現在未検出 (ハードウェア未接続またはファームウェア待ち — 正常)"
fi
