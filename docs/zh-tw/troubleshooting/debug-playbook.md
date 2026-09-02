# YU AI Manager 除錯手冊

## 快速開始

```bash
# 執行全部診斷
python debug_check.py

# 指定資料庫
python debug_check.py --db /path/to/tags.db

# 簡易檢查（略過語法/Extension）
python debug_check.py --quick
```

---

## 常見問題及處理方法

### 1. config.json 損壞（反斜線問題）

**症狀：** 伺服器啟動時出現 JSONDecodeError
**原因：** 手動輸入 Windows 路徑時 `\U`、`\w` 等成為無效跳脫
**處理：** 伺服器啟動時會自動修復。手動修復方法：
```bash
python -c "
from core.config import safe_load_json
data = safe_load_json('config.json')
print('OK' if data else 'FAILED')
"
```

### 2. scan-all 中特定資料夾被略過

**症狀：** 「全資料夾掃描」中部分資料夾未被處理
**確認步驟：**
```bash
# 確認 scan_roots 內容
python -c "
import json
c = json.load(open('config.json'))
for i, r in enumerate(c.get('scan_roots', [])):
    print(f'  [{i}] repr={repr(r)} len={len(r)}')
"
```
**檢查項目：**
- 路徑是否過短（是否僅為 `\\wsl.localhost\`）
- 末尾是否有 `\`
- `os.path.exists(path)` 是否傳回 True

### 3. QR 分享顯示「沒有內容」

**症狀：** QR 分享按鈕 → Positive/Negative 為空
**可能原因：**
1. `templates` 資料表中沒有記錄（meta_source=unknown）
2. API 回應的鍵不符（v2.7.0 已修復）

**確認：**
```bash
# 檢查檔案 ID 的範本是否存在
python -c "
import sqlite3
con = sqlite3.connect('tags.db')
file_id = 276323  # 有問題的 ID
row = con.execute('SELECT * FROM templates WHERE file_id=?', (file_id,)).fetchone()
print('templates:', 'EXISTS' if row else 'MISSING')
meta = con.execute('SELECT meta_source FROM files WHERE id=?', (file_id,)).fetchone()
print('meta_source:', meta[0] if meta else 'NOT FOUND')
"
```

### 4. WSL/UNC 路徑掃描失敗

**症狀：** `\\wsl.localhost\...` 路徑探測失敗
**確認：**
```bash
python -c "
import os
path = r'\\\\wsl.localhost\\Ubuntu\\home\\user\\...'
print(f'exists: {os.path.exists(path)}')
print(f'isdir: {os.path.isdir(path)}')
print(f'repr: {repr(path)}')
print(f'len: {len(path)}')
"
```
**注意：** `pathlib.Path.exists()` 在 WSL UNC 路徑上有 bug。請使用 `os.path.exists()`。

### 5. Extension 未載入

**症狀：** Extension 清單中不顯示
**確認：**
```bash
python debug_check.py  # 檢視 Extension 檢查部分
```
**檢查項目：**
- `extension.json` 或 `extension.yml` 是否存在
- JSON/YAML 是否有效（使用 `safe_load_config` 檢查）
- `name` 欄位是否存在

### 6. PIN 認證被鎖定

**症狀：** 5 次失敗 → 60 秒鎖定
**處理：** 等待 60 秒，或重新啟動伺服器以重設。
**確認：** 瀏覽器開發人員工具 → Network → 檢視 `/_pin_check` 的回應錯誤訊息

---

## 除錯日誌的閱讀方法

### 伺服器主控台輸出

```
[WARN] config.json had invalid escapes -- auto-repaired and saved
  → config.json 的反斜線自動修復已執行

[DEBUG] scan/start: raw=..., sanitized=...
  → 掃描開始時的路徑（原始值 → 清理後）

[DEBUG] scan-all root 0: repr=..., len=...
  → 全資料夾掃描時各根路徑的詳細資訊

[Scan] Auto-registered scan root: /path/to/dir
  → 掃描成功時的自動登錄

[DEBUG share] file_id=123, file_row=yes, tmpl=no
  → QR 分享 API：檔案存在但沒有範本

[ERROR] file.json: JSON parse failed: ...
  → safe_load_json 的解析錯誤（應用程式不會崩潰）
```

---

## 檔案結構與除錯對象

```
web_ui.py          ← 進入點（伺服器啟動）
core/
  config.py        ← 設定管理、safe_load_*
  server.py        ← PIN 認證、QuickLock
  scanner.py       ← 掃描引擎
  extensions.py    ← Extension 載入
  db.py            ← 資料庫連線管理
  schema.py        ← 資料表定義
routes/
  scan.py          ← 掃描 API
  search.py        ← 搜尋 API
  share.py         ← QR 分享 API
  tools.py         ← 工具 API + Inspect API
  debug.py         ← 除錯 API
  pages.py         ← 頁面路由
static/js/
  main.js          ← 主 UI（搜尋、模態視窗、QR、鍵盤）
  scan-banner.js   ← 掃描進度 + 捲動至頂端（全頁面）
```
