# ffmpeg 安裝指南

Tag Database 使用 ffmpeg 為影片檔案（WebM、MP4 等）產生縮圖。

## Windows

### 方式 1：Scoop（建議）
```powershell
# 安裝 Scoop（如未安裝）
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
irm get.scoop.sh | iex

# 安裝 ffmpeg
scoop install ffmpeg
```

### 方式 2：Chocolatey
```powershell
# 安裝 Chocolatey（如未安裝）
# 以系統管理員身分執行
Set-ExecutionPolicy Bypass -Scope Process -Force
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

# 安裝 ffmpeg
choco install ffmpeg
```

### 方式 3：手動下載
1. 下載：https://www.gyan.dev/ffmpeg/builds/
2. 解壓縮到 `C:\ffmpeg`
3. 加入 PATH：
   - 開啟「環境變數」
   - 編輯「Path」
   - 加入 `C:\ffmpeg\bin`
4. 重新啟動終端機

---

## macOS

### Homebrew（建議）
```bash
# 安裝 Homebrew（如未安裝）
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 安裝 ffmpeg
brew install ffmpeg
```

---

## Linux

### Ubuntu/Debian
```bash
sudo apt update
sudo apt install ffmpeg
```

### Fedora
```bash
sudo dnf install ffmpeg
```

### Arch
```bash
sudo pacman -S ffmpeg
```

---

## 驗證安裝

```bash
ffmpeg -version
```

應輸出版本資訊。

---

## 測試影片縮圖

```bash
# 啟動 WebUI
python web_ui.py --db tags.db

# 導覽到一個 WebM 檔案
# 縮圖應自動產生
```

---

## 疑難排解

### "ffmpeg not installed" 錯誤

**症狀**：影片縮圖顯示錯誤訊息

**解決方案**：
1. 驗證 ffmpeg 已安裝：`ffmpeg -version`
2. 重新啟動終端機/PowerShell
3. 重新啟動 WebUI
4. 檢查 PATH 設定

### 縮圖未產生

**症狀**：縮圖顯示「Failed to extract video frame」

**可能原因**：
- 影片檔案已損壞
- 不支援的影片編解碼器
- ffmpeg 逾時（>10 秒）

**除錯**：
```bash
# 手動測試
ffmpeg -i your_video.webm -ss 00:00:01 -vframes 1 test_thumb.jpg

# 檢查記錄檔
# 尋找 "[ERROR] ffmpeg" 訊息
```

---

## 選用：GPU 加速

用於更快的影片處理（進階）：

### Windows (NVIDIA)
```bash
# 下載 NVIDIA 組建：
# https://www.gyan.dev/ffmpeg/builds/
# 選擇 "ffmpeg-release-full.7z"
```

### macOS (VideoToolbox)
```bash
# Homebrew 組建中已包含
```

### Linux (VAAPI)
```bash
sudo apt install ffmpeg vainfo
```

---

## 效能說明

- 首次縮圖產生：約 1-3 秒
- 快取縮圖：<100ms
- ZIP 檔案：解壓縮到暫存目錄後處理
- 逾時：每個影片 10 秒

---

## 不安裝 ffmpeg

如果 ffmpeg 不可用：
- 影片檔案的縮圖將顯示錯誤
- 仍可透過中繼資料搜尋影片
- 建議安裝 ffmpeg 以獲得完整功能
