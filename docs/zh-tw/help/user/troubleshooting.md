# 疑難排解

## 常見問題

### 伺服器無法啟動

- 確認 Python 虛擬環境是否已啟用：`source venv/bin/activate`
- 確認相依套件是否已安裝：`uv pip install -r requirements.txt`
- 確認連接埠是否被佔用：`ss -tlnp | grep 5000`

### 圖片無法顯示

- 縮圖 API 需要圖片檔案的實體存在
- 確認 `files` 資料表的路徑是否與實際檔案路徑一致
- 確認掃描根目錄的路徑是否正確

### 無法從 LAN 存取

- 確認 Settings > Server 中「LAN Access」是否已開啟
- 確認是否已設定 PIN 認證（LAN 公開時為必要項目）
- 確認防火牆是否已開放該連接埠
- 確認伺服器的 IP 位址是否正確

### MCP 連線錯誤

- 確認 `YU_BASE_URL` 是否正確
- 確認伺服器是否正在執行
- 確認 API 金鑰是否有效
- 若透過 LAN 連線，確認 HTTP/SSE 端點 (`/mcp`) 是否可用

### 掃描速度緩慢

- 將 `compute_hash` 設為 OFF 可加快速度
- 若為遠端路徑，請調整 Remote FS 的逾時設定
- 大量檔案的初次掃描需要較長時間

### 縮圖生成緩慢

- 掃描中磁碟 I/O 會達到飽和，因此縮圖生成會變慢。掃描完成後會自動執行預熱
- **pyvips（選用）**：若有大量大型 JPEG 圖片，可透過 libvips 的 shrink-on-load 加速
  - Linux：`sudo apt install libvips-dev && uv pip install pyvips`
  - macOS：`brew install vips && uv pip install pyvips`
  - Windows：從 [libvips 發布頁面](https://github.com/libvips/libvips/releases) 下載 DLL 並加入 PATH 後執行 `uv pip install pyvips`
  - 若已安裝會自動偵測。未安裝時仍可使用 Pillow 運作
- **Pillow-SIMD（選用）**：透過 ARM NEON / x86 AVX2 將圖片縮放加速 2-4 倍
  - `uv pip install pillow-simd`（取代 Pillow 的直接替換套件）
  - ARM NEON 最佳化建置：`CC="cc -mfpu=neon" uv pip install --force-reinstall pillow-simd`
  - 在沒有預建 wheel 的環境中需要建置工具（gcc 等）

## 除錯

- 在 Settings > Logs 分頁確認伺服器日誌
- MCP 除錯模式：設定 `YU_DEBUG_MODE=1` 可使用額外工具
- DB 完整性檢查：`python db_health.py`
