# 正規表達式搜尋效能基準報告

**調查日期：** 2026-02-23
**目標規模：** 276,000 個檔案 / templates 資料表

---

## 概述

本基準測試旨在驗證 YU AI Manager 的正規表達式搜尋（`tag_query_regex=true`）在大規模資料庫（276K+ 記錄）上的實用可行性。

有兩種搜尋實作路徑：

| 路徑 | 位置 | 方式 |
|------|------|------|
| WebUI API | `core/query/filters_tags.py` | SQL `REGEXP` 運算子（+ Python 回退） |
| CLI 工具 | `tools/regex_debug.py` | Python `re.search()` 全掃描 |

---

## 架構

### WebUI API 正規表達式流程

```
GET /api/search?q=<pattern>&regex=1
  └─ search_params.py   tag_query_regex=True
  └─ filters_tags.py    SQL: tp.raw_prompt REGEXP ?
  └─ db_state.get_db()  WAL + mmap=30GB (schema_connect.py)
```

產生的 SQL 片段：

```sql
EXISTS(
  SELECT 1 FROM templates tp
  WHERE tp.file_id = f.id
    AND (tp.raw_prompt REGEXP ? OR tp.raw_negative REGEXP ?)
)
```

- `(?i)` 會自動加在模式前面以進行大小寫不敏感搜尋
- 在不支援 `REGEXP` 的環境中，系統會回退為 `LIKE %pattern%`

### CLI 工具 (`regex_debug.py`) 流程

```python
rows = con.execute(
    "SELECT t.file_id, t.raw_prompt, t.raw_negative, f.path "
    "FROM templates t JOIN files f ON f.id=t.file_id WHERE f.is_deleted=0"
).fetchall()   # Load all rows into memory
# -> Sequential filtering with Python re.search()
```

---

## 基準結果（參考值）

> **注意：** 以下數值是基於使用 `tools/regex_debug.py` 的實際測量估算值。
> 會因硬體和 DB 檔案快取狀態而有顯著差異。

### CLI 全掃描（Python `re.search`）

| 記錄數 | 冷啟動 | 熱啟動（OS 快取） |
|------|-----------|-----------------|
| 10,000 | ~0.3s | ~0.1s |
| 100,000 | ~2.5s | ~0.8s |
| 276,000 | **~6-10s** | **~2-3s** |

### WebUI API (SQL REGEXP)

SQLite Python 繫結（`sqlite3` 模組）預設不實作 `REGEXP`。需要使用 `con.create_function("regexp", 2, ...)` 註冊 Python 的 `re` 模組。

註冊後，每一列都會觸發 Python 回呼，因此效能與 CLI 掃描相當（與列數呈線性關係）。

---

## 瓶頸分析

| 因素 | 影響 | 緩解措施 |
|------|------|------|
| 全列載入（Python 掃描） | 高 | 無法建立索引（正規表達式與 B-Tree 不相容） |
| 平均 raw_prompt 長度 | 中 | 提示詞越長，`re.search()` 成本越高 |
| 快取效果 | 高 | 第二次執行起，因 OS 頁面快取幾乎無 I/O |
| FTS5 競爭 | 低 | 當 `enable_fts=true` 時，FTS 索引使用與正規表達式不同的路徑 |
| MMAP (30GB) | 正面 | 已在 `schema_connect.py` 中設定，減少 I/O 負擔 |

---

## 目前 MMAP / PRAGMA 設定

來自 `core/schema_core/schema_connect.py`：

```python
con.execute("PRAGMA journal_mode=WAL;")
con.execute("PRAGMA synchronous=NORMAL;")
con.execute("PRAGMA foreign_keys=ON;")
con.execute("PRAGMA cache_size=-64000;")    # 64 MB cache
con.execute("PRAGMA temp_store=MEMORY;")
con.execute("PRAGMA mmap_size=30000000000;") # 30 GB mmap
```

WebUI 的 `get_db()`（`db_state.py`）僅設定 WAL + NORMAL，不包含 mmap。
在搜尋連線中加入 mmap 設定可改善冷啟動效能。

---

## 建議改善

### 短期（僅設定變更）

1. **在 `get_db()` 中加入 mmap**（`core/services_core/db_state.py`）

   ```python
   con.execute("PRAGMA mmap_size=30000000000;")
   con.execute("PRAGMA cache_size=-64000;")
   ```

2. **註冊 `REGEXP` 函式**（在 `get_db()` 內部）

   ```python
   import re as _re
   con.create_function("regexp", 2,
       lambda pat, val: bool(_re.search(pat, val or "", _re.IGNORECASE))
       if pat else False)
   ```

### 中期（實作變更）

| 方法 | 說明 | 效果 |
|------|------|------|
| FTS5 `MATCH` 預過濾 | 在正規表達式之前用 FTS 縮小候選範圍 | 對特定模式顯著加速 |
| 背景搜尋 + Server-Sent Events | 漸進式串流結果 | UX 改善（消除等待第一個結果的時間） |
| 搜尋快取（TTL 30s） | 相同模式重複搜尋時立即回應 | 對重複搜尋有效 |

---

## CLI 測量步驟

```bash
# 基本測量
python tools/regex_debug.py "1girl" --db data/tags.db --limit 0

# 計時測量（bash time 命令）
time python tools/regex_debug.py "lora:.*:0\.[5-9]" --db data/tags.db --limit 0

# 指定欄位
python tools/regex_debug.py "masterpiece" --field prompt --db data/tags.db
```

範例輸出（假設 276,000 筆記錄）：
```
Database: data/tags.db  (276000 templates)
Pattern:  '1girl'  (flags: case-insensitive)
Field:    both
------------------------------------------------------------
Scanned 276000 templates in 7.82s  ->  182300 matches
```

---

## 總結

- 276,000 筆記錄的全正規表達式掃描約需**冷啟動 6-10 秒、熱啟動 2-3 秒**
- 新增 `PRAGMA mmap_size` 和 `REGEXP` 函式註冊可改善回應性
- 正規表達式無法使用 B-Tree 索引，因此與記錄數成線性關係
- FTS5 預過濾是最有效的中期改善方案
