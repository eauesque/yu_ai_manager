# CJK / 雙位元組編碼陷阱與解決方案

本文件整理了雙位元組字元環境（主要是日語 CP932/Shift-JIS）中特有的 bug，以及本專案中採用的解決方案。旨在為遇到類似問題的開發者和 AI 代理提供參考。

---

## 1. Windows 主控台 cp932 崩潰

### 症狀

Windows `cmd.exe` / PowerShell / Git Bash 的預設輸出編碼為 **cp932 (Shift-JIS)**。當 `print()` 輸出 cp932 中不存在的 Unicode 字元時，會立即引發 `UnicodeEncodeError` 導致崩潰。

```
UnicodeEncodeError: 'charmap' codec can't encode character '\u2014' in position 12
```

### 引發問題的字元

| 字元 | 名稱 | 使用場景 |
|------|------|---------|
| `—` (U+2014) | em dash | 日誌輸出分隔符 |
| `–` (U+2013) | en dash | 進度顯示 |
| `✓ ✗ ✅ ❌ ⚠️` | 勾選標記/表情符號 | 成功/失敗指示 |
| `🧹 📦 📁 🔍 🔧` | 表情符號 | 操作標籤 |
| `█ ░` | 區塊字元 | 進度條 |

### 解決方案

- **在 `print()` 中只使用 ASCII 安全字元**：`[OK]`、`[NG]`、`[!]`、`--`、`#`、`-` 等。
- `logging` 處理器同樣適用。編碼為 cp932 的處理器會遇到相同的問題。
- 可以透過設定 `PYTHONIOENCODING=utf-8` 來解決，但依賴使用者環境不夠可靠。防禦性地使用 ASCII 更為安全。

### 影響範圍

本專案需要對 **19 個檔案**進行批次修復（v2.28.0）。AI 程式碼生成器（Claude/GPT）高頻使用表情符號和 em dash。**這是審查 AI 生成程式碼時最需要檢查的項目之一。**

---

## 2. ZIP 檔案名稱亂碼（CP437）

### 症狀

在舊版 Windows 系統（95/98/XP 時代）建立的 ZIP 檔案以 **Shift-JIS (CP932)** 儲存檔案名稱，但 ZIP 規格不包含編碼中繼資料。Python 的 `zipfile` 模組在 UTF-8 旗標（第 11 位元）未設定時將檔案名稱解碼為 **CP437**。這會導致日語檔案名稱變成 `âwâCâèâb` 這樣的亂碼。

### 解決方案：10 級回退鏈

`core/infra_core/encoding.py` 定義了優先順序排列的 CJK 編碼清單：

```
UTF-8（zipfile 首先嘗試）→ CP932 → EUC-JP → ISO-2022-JP
→ EUC-KR → CP949 → GB2312 → GBK → Big5 → CP950
```

- **不使用** `chardet` / `cchardet`：短檔案名稱（10--30 位元組）會產生過多誤判。
- 固定優先順序方式提供更好的可重現性和更簡單的除錯。

### Python 3.11+ 的 `metadata_encoding` 參數

```python
# Python 3.11+ 允許透過 metadata_encoding 直接指定
zf = zipfile.ZipFile(path, metadata_encoding='cp932')
```

此方法無法處理以 CP932 以外編碼儲存的 ZIP 檔案。失敗時，程式碼會在不使用 `metadata_encoding` 的情況下重新開啟封存檔，並透過 `repair_cp437_name()` 嘗試恢復。

### 7z 封存檔

7-Zip 有自己的檔案名稱處理方式。透過 7z CLI 可能出現 CP437 亂碼；`repair_cp437_name()` 套用相同的恢復邏輯。

---

## 3. 雙位元組檔案名稱導致 ZIP/7z 掃描卡住

### 症狀

當 `zipfile.ZipFile()` 讀取 Shift-JIS 編碼檔案名稱的舊 ZIP 中央目錄時，可能進入阻斷 I/O 狀態而卡住。檔案數量多的封存檔尤其容易出現此問題。

### 解決方案

1. **逾時保護**：引入了 `run_with_timeout()` 守護執行緒輔助函式。
   - 檔案清單：30 秒
   - 掃描 I/O：60 秒
2. **scan_errors 資料表**（遷移 v24）：逾時和編碼錯誤被持久化到資料庫中。
   - 錯誤類型分類：`encoding` / `timeout` / `scan` / `archive_scan` / `archive_timeout` / `filesystem`

---

## 4. SQLite FTS5 tokenchars 引號問題

### 症狀

根據 `tokenchars` 選項使用的引號組合，可能在 SQLite FTS5 `tokenize` 指令中觸發解析錯誤。

```sql
-- NG：外層單引號 + 內層雙引號 → 解析錯誤
tokenize='unicode61 tokenchars "_:."'

-- OK：外層雙引號 + 內層單引號
tokenize="unicode61 tokenchars '_:.'"
```

### 原因

FTS5 分詞器解析器無法正確解析巢狀在單引號內的雙引號。可能還存在版本特定的行為差異（在 SQLite 3.45.1 上確認）。

### 解決方案

使用 Python 三引號字串以相容兩種 SQL 引號類型：

```python
# OK：Python ''' 包裹 SQL 的 " 和 '
con.execute('''
    CREATE VIRTUAL TABLE fts USING fts5(
        col1,
        tokenize="unicode61 tokenchars '_:.'"
    )
''')
```

### 發現經過

此問題在重建 FTS5 資料表的遷移 29 中被發現。AI 生成的程式碼使用了單引號外層語法。在 SQLite 3.45.1 上伺服器啟動時崩潰（v2.70.1 中修復）。

---

## 5. UTF-16 編碼的 WebP EXIF

### 症狀

部分影像生成工具（尤其是 NAI 系列工具）以 **UTF-16（帶 BOM）** 儲存 WebP EXIF 中繼資料。標準 UTF-8 解碼會產生亂碼。

### 解決方案

- 偵測 BOM（位元組順序標記）以判斷 UTF-16 BE/LE。
- 無 BOM 時使用啟發式方法推測 BE/LE。
- 依序回退到 UTF-8 和 latin-1。

---

## 6. PNG tEXt 區塊編碼

### 症狀

PNG 規格將 tEXt 區塊定義為 **Latin-1 (ISO-8859-1)**，但大多數 AI 影像生成工具直接寫入 UTF-8 編碼的字串。以 `latin-1` 解碼會導致日語文字亂碼。

### 解決方案

先嘗試 UTF-8 解碼，失敗時回退到 latin-1：

```python
try:
    text = raw_bytes.decode('utf-8')
except UnicodeDecodeError:
    text = raw_bytes.decode('latin-1')
```

---

## 7. config.json 中的 Windows 路徑反斜線

### 症狀

Windows 檔案路徑包含反斜線（`\`）。在 JSON 檔案中手動輸入路徑會產生無效的跳脫序列。

```json
{"scan_roots": ["C:\Users\test"]}  // \U 和 \t 會變成跳脫序列
```

### 解決方案

- `_repair_json_backslashes()` 在伺服器啟動時自動修復路徑。
- 路徑在儲存前會進行內部正規化。

---

## 8. pathlib 與 WSL UNC 路徑

### 症狀

在 WSL（Windows Subsystem for Linux）下，`pathlib.Path.exists()` 對 UNC 路徑（`\\server\share\...`）可能傳回錯誤的結果。

### 解決方案

- UNC 路徑的存在性檢查使用 `os.path.exists()`。
- `pathlib` 雖然方便，但對網路路徑不可靠。

---

## 9. CSV 匯出的 UTF-8 BOM

### 症狀

Excel 會將沒有 BOM 的 UTF-8 CSV 檔案顯示為亂碼。Excel 將無 BOM 的 UTF-8 解讀為 ANSI（日語環境中為 CP932）。

### 解決方案

```python
buf.write("\ufeff")  # 用於 Excel 相容性的 UTF-8 BOM
```

在 CSV 輸出前加上 BOM（`\ufeff`）。這可確保 Excel 將檔案識別為 UTF-8。

---

## 10. JSON 輸出中的 `ensure_ascii=False`

### 症狀

Python 的 `json.dumps()` 預設將非 ASCII 字元跳脫為 `\uXXXX`。包含日語標籤名稱或檔案路徑的 MCP 工具回應會顯示為 `\u30bf\u30b0`，使 AI 代理難以理解內容。

### 解決方案

```python
json.dumps(data, ensure_ascii=False, indent=2)
```

本專案在所有 MCP 工具模組（10 個檔案）中一致使用此設定。

---

## 11. 資料夾選取對話方塊輸出解碼

### 症狀

Windows 上的 PowerShell 資料夾選取對話方塊以 CP932 編碼傳回 `subprocess` 輸出。預設的 UTF-8 解碼會引發 `UnicodeDecodeError`。

### 解決方案

```python
result = subprocess.run(..., capture_output=True)
path = result.stdout.decode('cp932', errors='replace').strip()
```

`errors='replace'` 旗標確保即使解碼失敗也能安全處理。

---

## AI 代理注意事項

上述許多問題都是 **AI 程式碼生成器容易忽略的模式**：

1. **不要在 `print()` 中使用表情符號或裝飾字元** -- AI 生成器經常為了視覺效果而使用它們。
2. **不要假設檔案名稱編碼** -- 基於 UTF-8 假設撰寫的程式碼在 CP932 環境中會出錯。
3. **在實際執行階段測試 SQLite 引號** -- 符合文件的語法在實務中仍可能失敗。
4. **始終向 `json.dumps()` 傳遞 `ensure_ascii=False`** -- 處理日語資料時不可或缺。
5. **使用環境編碼解碼 subprocess 輸出** -- Windows 通常使用 CP932。
6. **在 CSV 輸出中包含 BOM** -- 這是 Excel 相容性所必需的。

---

## 參考：本專案相關檔案

| 檔案 | 說明 |
|------|------|
| `core/infra_core/encoding.py` | CJK 回退鏈、CP437 亂碼修復 |
| `core/schema_core/schema_migrate_steps_29.py` | 正確的 FTS5 tokenchars 引號 |
| `core/tools/fs_dialog.py` | 資料夾選取對話方塊 CP932 解碼 |
| `core/configuration/json_rw.py` | config.json 反斜線修復 |
| `routes/collections.py` | CSV 匯出 BOM 插入 |
| `CLAUDE.md` | 「Windows 環境注意事項 > 主控台輸出」部分 |
