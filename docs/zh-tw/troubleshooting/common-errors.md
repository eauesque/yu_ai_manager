# Tag Database - 除錯檢查清單

**依優先順序排列的除錯清單**
**狀態**：舊版（記錄於 v2.5.x 時期；所有項目均已解決）
**最後更新**：2026-02-13

---

## P0（緊急）：立即修復（影響可用性）

### 1. UI 版面對齊修復

**問題：**
```
搜尋欄位並排放置時會溢出，
導致按鈕位置偏移。
```

**驗證方法：**
1. 啟動 WebUI
2. 將瀏覽器調整為 1366x768
3. 檢查搜尋欄位對齊

**修復位置：** `templates/index.html`
```html
<!-- 修改前 -->
<div class="search-row">
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
</div>

<!-- 修改後 -->
<div class="search-row">
  <!-- 新增 flex-wrap: wrap -->
  <div class="form-group" style="flex: 1 1 200px;">...</div>
  ...
</div>
```

**驗證：**
- [ ] 在 1920x1080 下正確顯示
- [ ] 在 1366x768 下正確顯示
- [ ] 在 768x1024（平板）下正確顯示

---

### 2. 標籤自動補全去重

**問題：**
```
自動補全建議中包含重複項目。

範例：
  sample_creator_a,sample_creator_b,sample_creator_c
  sample_creator_a, sample_creator_b, sample_creator_c
  ^ 僅空格不同
```

**驗證方法：**
1. 在標籤輸入欄位中輸入 "sample_creator"
2. 檢查自動補全建議
3. 查看是否有重複

**修復位置：** `static/js/main/main.js`
```javascript
// initTagAutocomplete() 內部
async function fetchSuggestions(q) {
  const response = await fetch(`/api/suggest?q=${encodeURIComponent(q)}`);
  const data = await response.json();

  // 正規化並去重
  const normalized = new Map();

  for (const item of data) {
    const clean = item.tag
      .replace(/,(?!\s)/g, ', ')  // 逗號後新增空格
      .replace(/\s+/g, ' ')        // 合併多個空格
      .trim();

    if (!normalized.has(clean)) {
      normalized.set(clean, item.count);
    } else {
      // 合併計數
      normalized.set(clean, normalized.get(clean) + item.count);
    }
  }

  return Array.from(normalized.entries()).map(([tag, count]) => ({
    tag,
    count
  }));
}
```

**驗證：**
- [ ] 無剩餘重複項目
- [ ] 計數正確合併
- [ ] 無效能問題

---

## P1（高）：改進（影響功能）

### 3. 搜尋中的括號正規化

**問題：**
```
驗證 \(tag\) 和 (tag) 是否被同等對待。
```

**驗證方法：**
1. 準備帶有 `\(emphasis\)` 標籤的影像
2. 在搜尋框中搜尋 `(emphasis)`
3. 檢查影像是否出現在結果中

**檢查點：**
- [ ] 搜尋 `(tag)` 也能比對 `\(tag\)`
- [ ] 搜尋 `\(tag\)` 也能比對 `(tag)`
- [ ] 正規表示式模式不套用此正規化

**相關程式碼：** `web_ui.py` - `normalize_tag_for_search()`

---

### 4. ZIP 內部檔案讀取測試

**問題：**
```
驗證 ZIP 封存檔內的影像能正確顯示，
且中繼資料能正確擷取。
```

**測試案例：**

#### 測試 1：基本操作
```bash
# 1. 建立測試 ZIP
zip test.zip image1.png image2.png

# 2. 掃描
python tagdb_tool.py scan --db test.db --root . --scan-zips

# 3. 驗證
python tagdb_tool.py search --db test.db --q "*"
```

**確認項目：**
- [ ] ZIP 內檔案登錄為 `test.zip!image1.png`
- [ ] 中繼資料已擷取
- [ ] 縮圖已顯示

#### 測試 2：擷取功能
```
1. 在 WebUI 中開啟 ZIP 內檔案
2. 點選「擷取並編輯」按鈕
3. 驗證檔案管理員是否開啟
4. 驗證擷取的檔案是否存在
```

**確認項目：**
- [ ] 擷取按鈕可見
- [ ] 點選後開啟檔案管理員
- [ ] 檔案被擷取到 extracted/ 目錄
- [ ] 擷取的檔案已登錄到資料庫

#### 測試 3：大型 ZIP
```bash
# 1) 建立 1.1 GB ZIP（Zip64）
mkdir -p /tmp/tagdb_largezip_test/input
python - <<'PY'
from pathlib import Path
import base64
Path('/tmp/tagdb_largezip_test/input/sample.png').write_bytes(
    base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+X2foAAAAASUVORK5CYII=')
)
PY
truncate -s 1100M /tmp/tagdb_largezip_test/input/payload.bin
python - <<'PY'
import zipfile
from pathlib import Path
root = Path('/tmp/tagdb_largezip_test')
with zipfile.ZipFile(root / 'large_1_1gb.zip', 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as z:
    z.write(root / 'input' / 'sample.png', arcname='images/sample.png')
    z.write(root / 'input' / 'payload.bin', arcname='payload/payload.bin')
print((root / 'large_1_1gb.zip').stat().st_size)
PY

# 2) 掃描 ZIP
/usr/bin/time -f 'elapsed=%E maxrss_kb=%M' \
  python tagdb_tool.py scan --db /tmp/tagdb_largezip_test/largezip.db \
  --root /tmp/tagdb_largezip_test --recursive --scan-zips
```

**確認項目：**
- [x] 記憶體使用量在正常範圍內
- [x] 掃描在可接受時間內完成（5 分鐘以內）
- [x] 無錯誤

**量測結果（2026-02-17）：**
- ZIP 大小：`1,153,433,914 bytes`（約 1.1 GB）
- 耗時：`elapsed=0:00.14`
- 尖峰 RSS：`maxrss_kb=23864`
- 資料庫記錄：`zip_members=1`（`large_1_1gb.zip!images/sample.png`）

---

### 5. 檢查點搜尋測試

**問題：**
```
驗證模型名稱能正確擷取和搜尋。
```

**測試案例：**

#### 測試 1：模型名稱擷取
```python
# 各格式的擷取驗證

# NovelAI
metadata = {"model": "nai-diffusion-3"}
→ model_name: "nai-diffusion-3"

# SD
metadata = {"Model": "animagine-xl-3.1", "Model hash": "abc123"}
→ model_name: "animagine-xl-3.1", model_hash: "abc123"

# ComfyUI
metadata = {"checkpoint": "ponyDiffusionV6XL.safetensors"}
→ model_name: "ponyDiffusionV6XL"
```

**確認項目：**
- [ ] NovelAI 格式擷取正常
- [ ] SD 格式擷取正常
- [ ] ComfyUI 格式擷取正常

#### 測試 2：搜尋功能
```
1. 在 WebUI 中點選檢查點輸入欄位
2. 驗證自動補全是否出現
3. 搜尋 "animagine"
4. 驗證是否只顯示該模型的影像
```

**確認項目：**
- [ ] 自動補全正常運作
- [ ] 部分比對正常運作
- [ ] 結果依使用頻率排序

---

## P2（中等）：未來工作（效能改進）

### 6. 縮圖快取實作

**問題：**
```
ZIP 內檔案的縮圖每次請求都會重新產生。
速度很慢。
```

**建議實作：**
```python
# web_ui.py
import hashlib

CACHE_DIR = Path("cache/thumbnails")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

@app.route("/api/thumbnail/<int:file_id>")
def api_thumbnail(file_id):
    # 產生快取路徑
    cache_key = hashlib.md5(f"{file_id}".encode()).hexdigest()
    cache_path = CACHE_DIR / f"{cache_key}.jpg"

    # 如果快取版本可用則傳回
    if cache_path.exists():
        return send_file(cache_path, mimetype='image/jpeg')

    # 否則產生
    thumbnail = generate_thumbnail(...)

    # 儲存到快取
    thumbnail.save(cache_path, 'JPEG', quality=85)

    return send_file(cache_path, mimetype='image/jpeg')
```

**驗證：**
- [ ] 第二次存取明顯更快
- [ ] 磁碟使用量可接受
- [ ] 快取清除正常運作

---

### 7. 大規模效能量測

**測試案例：**

#### 測試 1：100,000 個檔案
```bash
# 量測掃描時間
time python tagdb_tool.py scan --db large.db --root /path/to/100k --recursive

# 量測搜尋時間
time python tagdb_tool.py search --db large.db --q "1girl"
```

**目標：**
- [ ] 掃描：每小時至少 50,000 個檔案
- [ ] 搜尋：1 秒以內（在 100,000 個檔案中）

#### 測試 2：WebUI 回應性
```
1. 使用 100,000 個檔案的資料庫啟動 WebUI
2. 執行搜尋
3. 捲動瀏覽結果
```

**確認項目：**
- [ ] 搜尋結果在 3 秒內顯示
- [ ] 捲動流暢
- [ ] 瀏覽器不卡頓

---

## 測試執行檢查清單

### 環境設定
- [ ] Python 3.8+ 已安裝
- [ ] 相依性已安裝
- [ ] 測試資料已準備（各格式的影像）

### 功能測試
- [ ] ZIP 讀取
- [ ] 多目錄掃描
- [ ] 標籤正規化
- [ ] 檢查點搜尋
- [ ] 模型篩選

### UI/UX 測試
- [ ] 版面（多解析度）
- [ ] 深色模式
- [ ] 鍵盤快速鍵
- [ ] 自動補全

### 效能測試
- [ ] 10,000 個檔案
- [ ] 50,000 個檔案
- [ ] 100,000 個檔案
- [ ] 大型 ZIP（500 MB+）

### 瀏覽器相容性
- [ ] Chrome/Edge
- [ ] Firefox
- [ ] Safari

### 作業系統相容性
- [ ] Windows 10/11
- [ ] macOS
- [ ] Linux (Ubuntu)

---

## 除錯工具

### 啟用日誌
```bash
# 在 tagdb_tool.py 頂端新增
import logging
logging.basicConfig(level=logging.DEBUG)
```

### 效能量測
```python
import time

start = time.time()
# ... 處理 ...
print(f"Time: {time.time() - start:.2f}s")
```

### 記憶體使用量檢查
```python
import tracemalloc

tracemalloc.start()
# ... 處理 ...
current, peak = tracemalloc.get_traced_memory()
print(f"Memory: {peak / 1024 / 1024:.2f} MB")
tracemalloc.stop()
```

---

**建立日期：** 2026-02-13
**優先順序：** P0 → P1 → P2
**注意：** 此檢查清單建立於 v2.5.x 時期。所有列出的項目均已解決。
