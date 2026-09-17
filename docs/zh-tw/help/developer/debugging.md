# 除錯手冊

YU AI Manager 的綜合除錯指南。
面向開發者和 AI 代理，幫助高效調查和修復 bug。

---

## 目錄

1. [啟動伺服器](#啟動伺服器)
2. [除錯記錄](#除錯記錄)
3. [執行測試](#執行測試)
4. [DB 除錯](#db-除錯)
5. [驗證繞過與測試](#驗證繞過與測試)
6. [MCP 除錯](#mcp-除錯)
7. [前端除錯](#前端除錯)
8. [環境變數](#環境變數)
9. [常見錯誤與解決方案](#常見錯誤與解決方案)
10. [效能除錯](#效能除錯)

---

## 啟動伺服器

### 開發模式（建議）

不使用 PIN 驗證啟動，用於本機除錯：

```bash
source venv/Scripts/activate  # Windows Git Bash
python web_ui.py --db ./tags.db --config config_test.json --port 5100
```

如果 `config_test.json` 不存在，建立以下內容：

```json
{
  "scan_roots": [],
  "server": {
    "host": "127.0.0.1",
    "port": 5100,
    "lan": false
  },
  "extract_a1111": true,
  "extract_comfyui": true,
  "lowercase_tags": true,
  "compute_hash": false,
  "enable_fts": true,
  "extensions": {}
}
```

### 正式模式（LAN 暴露）

```bash
python web_ui.py --db ./tags.db --host 0.0.0.0 --port 5000 --pin 1234
```

> **注意**：繫結到 `0.0.0.0` 時需要 PIN。自 v4.8.1 起，LAN 暴露時 `--debug` 標誌被忽略（防止堆疊追蹤洩漏）。

### 連接埠選擇

5100 -> 5200 -> 5300 -> 每次遞增 100。啟動前先確認：

```bash
# Windows
netstat -ano | grep :5100

# Linux/macOS
ss -tlnp | grep :5100
```

### CLI 選項

| 選項 | 類型 | 預設值 | 說明 |
|--------|------|---------|------|
| `--db` | path | `data/tags.db` | SQLite DB 檔案路徑 |
| `--config` | path | `config.json` | 設定檔路徑 |
| `--host` | str | `127.0.0.1` | 繫結位址 |
| `--port` | int | 5000 | 繫結連接埠 |
| `--lan` | flag | - | 繫結到 `0.0.0.0`（LAN 存取） |
| `--pin` | str | - | 啟用 PIN 驗證 |
| `--debug` | flag | - | 啟用 Quart 除錯模式 |
| `--debug-log` | `on`/`off` | - | 啟用/停用結構化除錯記錄 |
| `--debug-log-file` | path | `logs/debug.log` | 記錄檔輸出路徑 |
| `--debug-log-max-mb` | int | 10 | 記錄輪替大小（MB） |
| `--debug-log-backups` | int | 5 | 記錄備份代數 |
| `--debug-log-stdout` | `on`/`off` | `on` | 同時輸出到 stderr |
| `--allow-restart` | flag | - | 啟用 `/api/server/restart` |
| `--trusted-proxy-auth` | flag | - | 啟用 Trusted Proxy 驗證 |
| `--profile` | str | - | 啟動設定檔名稱 |

### launch-args.txt

在專案根目錄放置 `launch-args.txt`，啟動時自動載入引數。CLI 引數優先。

---

## 除錯記錄

### 啟用

```bash
# 透過 CLI
python web_ui.py --db ./tags.db --debug-log on

# 透過環境變數
export TAGDB_DEBUG=1
python web_ui.py --db ./tags.db
```

### 記錄格式

透過 `dlog()` 函式（`core/infra_core/debug_log.py`）產生結構化除錯記錄：

```
[DEBUG] 2026-03-15 12:34:56 | scan:prepare | counting_start | root=/path/to/dir, recursive=True
```

格式：`[DEBUG] 時間戳 | 來源 | 事件名稱 | key=value, ...`

### 即時監控

```bash
# 追蹤記錄檔
tail -f logs/debug.log

# 透過 API
curl http://127.0.0.1:5100/api/debug/logs

# SSE 串流
curl -N "http://127.0.0.1:5100/api/debug/logs?stream=1"
```

### 記錄環形緩衝區

執行中的記錄也儲存在記憶體內的環形緩衝區中（最多 1000 筆）。伺服器重啟後會遺失；如需持久化請使用檔案記錄。

---

## 執行測試

### 單元測試

```bash
source venv/Scripts/activate

# 執行所有測試
python -m pytest tests/test_basic.py -v

# 僅執行特定測試
python -m pytest tests/test_basic.py::TestImports -v

# 遇到第一個失敗即停止
python -m pytest tests/test_basic.py -x
```

### API 整合測試

```bash
python -m pytest tests/api/ -v
```

### Playwright 瀏覽器測試

```bash
# 1. 啟動測試伺服器
python web_ui.py --db ./tags.db --config config_test.json --port 5100 &

# 2. 執行測試
TARGET_URL=http://localhost:5100 python -m pytest tests/test_webui_browser.py -v
```

### 測試輸出

- 截圖：`screenshots/`
- 報告：`reports/`

---

## DB 除錯

### 檢查架構版本

```bash
python -c "
import sqlite3
con = sqlite3.connect('data/tags.db')
v = con.execute('SELECT MAX(version) FROM schema_version').fetchone()[0]
print(f'Schema version: {v}')
"
```

### 健康檢查

```bash
python db_health.py --db ./tags.db
```

### 除錯 SQL 執行

僅在 `YU_DEBUG_MODE=1` 時可用：

```bash
curl -X POST http://127.0.0.1:5100/api/debug/query \
  -H "Content-Type: application/json" \
  -H "X-Requested-With: XMLHttpRequest" \
  -d '{"sql":"SELECT COUNT(*) as cnt FROM files WHERE is_deleted=0"}'
```

> **注意**：自 v4.8.1 起，僅允許 SELECT 語句。

### 實用調查查詢

```sql
-- 依來源分類的檔案數
SELECT meta_source, COUNT(*) as cnt FROM files WHERE is_deleted=0 GROUP BY meta_source;

-- 模型使用排名
SELECT model_name, COUNT(*) as cnt FROM templates GROUP BY model_name ORDER BY cnt DESC LIMIT 20;

-- 孤立標籤
SELECT t.id, t.name FROM tags t LEFT JOIN file_tags ft ON t.id=ft.tag_id WHERE ft.tag_id IS NULL;

-- 重複路徑偵測
SELECT path, COUNT(*) as cnt FROM files GROUP BY path HAVING cnt > 1;
```

### DB 連線規則

| 函式 | 用途 | 使用情境 |
|----------|---------|------|
| `get_readonly_db()` | 唯讀 | GET API、搜尋、縮圖、統計 |
| `get_db()` | 讀寫（Row factory） | POST/PUT/DELETE API |
| `get_raw_db()` | 讀寫（無 Row factory） | 批次處理、掃描、遷移 |

> **重要**：在唯讀 API 中使用 `get_db()` 會導致掃描期間的寫入鎖競爭，阻塞檢視器數秒。務必使用 `get_readonly_db()`。

---

## 驗證繞過與測試

### 跳過 PIN 驗證

使用 `config_test.json`（未設定 PIN）啟動以跳過所有驗證。

### API 金鑰測試

```bash
# Bearer 權杖請求（不需要 CSRF 標頭）
curl -H "Authorization: Bearer sk_xxxxxxxxxxxxxx" \
  http://127.0.0.1:5000/api/stats/all
```

### API 金鑰作用域

自 v4.8.1 起，未指定作用域的金鑰預設為**唯讀**。

| 作用域 | 允許的操作 |
|-------|-------------------|
| `read` | 搜尋、檔案詳情、縮圖、統計 |
| `rate` | 評分設定/取得/批次 |
| `tag.write` | 標籤新增/移除 |
| `collection.write` | 收藏集 CRUD、我的最愛 |
| `annotate` | 註解讀取/寫入 |
| `scan` | 掃描啟動/取消/繼續 |
| `admin` | API 金鑰管理、設定、備份/還原 |

### 驗證鏈順序

```
static → /s/ (LAN Share) → /_pin → API Key Bearer
→ QuickLock → Trusted Proxy → session → cookie → PIN 頁面
```

---

## MCP 除錯

### 啟動 MCP 伺服器

```bash
source venv/Scripts/activate
python -m mcp_server
```

### 啟用除錯工具

```bash
export YU_DEBUG_MODE=1
export YU_BASE_URL=http://127.0.0.1:5100
export YU_API_KEY=sk_...
python -m mcp_server
```

### 除錯工具（9 個工具，YU_DEBUG_MODE=1）

| 工具 | 用途 |
|------|---------|
| `debug_health_check` | 伺服器、DB 和資料表健康檢查 |
| `debug_validate_counts` | API 統計與 DB 實際計數比較 |
| `debug_validate_search` | 搜尋 API 回歸檢查 |
| `debug_validate_collection` | 收藏集計數一致性 |
| `debug_validate_annotations` | 註解資料表完整性 |
| `debug_sample_files` | 隨機抽樣欄位分析 |
| `debug_roundtrip_test` | 註解/評分/標籤往返測試 |
| `debug_readonly_query` | 執行任意 SELECT 查詢 |
| `debug_full_report` | 工具 1-5 的綜合報告 |

### 匯入檢查

```bash
python -c "from mcp_server.server import mcp; print('OK')"
```

---

## Extension 安全掃描

YU AI Manager 內建了 Extension 的程式碼掃描功能。掃描**在 Extension 載入時自動執行**，因此在新增或修改 Extension 後，重新啟動伺服器即可觸發掃描。

### 自動掃描的運作方式

Extension 載入時依序執行以下檢查：

```
1. ManifestAuthority.review()   — Manifest 審查（格式、權限有效性）
2. CodeVerifier.verify()        — AST 靜態分析（所有 .py 檔案的程式碼掃描）
3. User consent check           — 權限核准/拒絕
4. Capability Token issuance    — 執行權限權杖
```

### CodeVerifier 偵測的內容

| 類別 | 目標 | 嚴重程度 |
|----------|--------|----------|
| 危險模組 | `subprocess`、`ctypes`、`importlib` | block |
| 直接 DB 存取 | `import sqlite3`（應使用 SandboxedDB） | block |
| 網路 | `requests`、`urllib`、`httpx`、`aiohttp`、`socket` | warn |
| 動態程式碼執行 | `eval()`、`exec()`、`__import__()`、`compile()` | block |

偵測到 `block` 嚴重程度的結果時，Extension 將被拒絕載入。

### 如何執行掃描

**正常流程（建議）：**

新增或修改 Extension 後重新啟動伺服器。掃描在載入期間自動執行，結果輸出到記錄中。

```bash
# 重新啟動伺服器以重新載入 Extension（掃描自動執行）
python web_ui.py --db ./tags.db --config config_test.json --port 5100
```

**僅手動掃描：**

```python
from pathlib import Path
from core.extensions_core.validation.code_verifier import CodeVerifier

result = CodeVerifier().verify(Path("extensions/my-extension"))

# Check results
for finding in result.findings:
    print(f"[{finding.severity}] {finding.file}:{finding.line} - {finding.message}")

print(f"Approved: {result.approved}")
```

### 信任等級

Extension 分為 3 個信任等級：

| 等級 | 條件 | 限制 |
|-------|-----------|-------------|
| L0 Trusted | `builtin-` 前綴 | 無限制 |
| L1 Verified | 簽章已驗證 | 僅限宣告的權限 |
| L2 Untrusted | 手動安裝 | 宣告的權限 + 需要使用者同意 |

### 執行時保護

載入後在執行時持續保護：

- **Import Guard**：透過 `sys.meta_path` 阻止未授權的模組匯入
- **Integrity Monitor**：每 5 分鐘比較 SHA-256 雜湊值以偵測檔案竄改
- **權杖自動撤銷**：偵測到違規時撤銷 Capability Token，停止執行

### 相關文件

| 文件 | 位置 |
|----------|----------|
| 三權分立安全模型 | `docs/development/development_docs/EXTENSION_TRIAS_POLITICA_SPEC.md` |
| 沙箱規格 | `docs/development/development_docs/EXTENSION_SANDBOX_SPEC.md` |
| Hook 規格 | `docs/development/development_docs/EXTENSION_HOOKS_SPEC.md` |

---

## 前端除錯

### TypeScript 建置

```bash
pnpm run build        # esbuild bundle
pnpm run typecheck    # tsc --noEmit (type check only)
```

輸出：`ui/default/static/dist/`（已加入 gitignore）

### CSRF 攔截器

`src/ts/nav/csrf-fetch.ts` 使用 Proxy 包裝全域 `fetch`，自動在所有 POST/PUT/DELETE 請求中注入 `X-Requested-With` 標頭。

### SSE 共用引擎

`window.EventSource` 被 Proxy 覆寫。直接 `new EventSource()` 會拋出錯誤。

```javascript
// 正確
window.sseSubscribe('scan.progress', (d) => console.log(d.data));

// 錯誤（執行時錯誤）
// new EventSource('/api/events/...')
```

### i18n 除錯

```javascript
window.setLang('en');
console.log(window.tr('search.count.normal', { count: 5 }));
```

---

## 環境變數

### 除錯 / 記錄

| 變數 | 值 | 預設值 | 說明 |
|----------|--------|---------|------|
| `TAGDB_DEBUG` | `1`/`0` | `0` | 啟用結構化除錯記錄 |
| `TAGDB_DEBUG_LOG` | path | `logs/debug.log` | 記錄檔路徑 |
| `TAGDB_DEBUG_LOG_MAX_MB` | int | `10` | 記錄輪替大小（MB） |
| `TAGDB_DEBUG_LOG_BACKUPS` | int | `5` | 備份代數 |
| `TAGDB_DEBUG_STDOUT` | `1`/`0` | `1` | 輸出到 stderr |

### 伺服器

| 變數 | 值 | 說明 |
|----------|--------|------|
| `TAGDB_DB` | path | DB 檔案路徑 |
| `TAGDB_CONFIG` | path | config.json 路徑 |
| `TAGDB_PROFILE` | str | 啟動設定檔名稱 |
| `TAGDB_ALLOW_RESTART` | `1`/`0` | 啟用重啟 API |

### MCP

| 變數 | 值 | 說明 |
|----------|--------|------|
| `YU_DEBUG_MODE` | `1` | 註冊 9 個除錯工具 |
| `YU_BASE_URL` | URL | MCP 用戶端基礎 URL |
| `YU_API_KEY` | `sk_...` | MCP 用戶端 API 金鑰 |

---

## 常見錯誤與解決方案

### 伺服器啟動

| 錯誤 | 原因 | 修復 |
|-------|-------|-----|
| `Address already in use` | 連接埠佔用 | 使用 `--port 5200` |
| `database is locked` | DB 鎖競爭 | 確保 DB 在本機磁碟上 |
| `--pin is required` | 無 PIN 的 LAN 繫結 | 加入 `--pin <digit>` |
| `ModuleNotFoundError` | venv 未啟用 | `source venv/Scripts/activate && uv pip install -r requirements.txt` |

### 驗證

| 錯誤 | 原因 | 修復 |
|-------|-------|-----|
| PIN 頁面迴圈 | Cookie 問題 | 在 DevTools 中檢查 Cookie |
| `CSRF header missing` (403) | 缺少 `X-Requested-With` | 在 fetch 請求中加入標頭 |
| API 金鑰被拒 | 作用域不足 | 指派所需的作用域（v4.8.1+） |

### Windows 特定問題

| 錯誤 | 原因 | 修復 |
|-------|-------|-----|
| `UnicodeEncodeError` on print | cp932 編碼 | 使用 ASCII 安全字元 |
| `pkill` 不起作用 | Git Bash 限制 | 使用 `taskkill //F //PID <pid>` |

---

## 效能除錯

### 掃描期間檢視器阻塞

**症狀**：掃描期間圖片載入停止 5-10 秒

**原因**：唯讀 API 使用了 `get_db()`（可寫入的連線）

**修復**：所有唯讀 API 使用 `get_readonly_db()`

### 速率限制

| 層級 | 目標 | 限制 |
|------|--------|-------|
| **HEAVY** | 相似搜尋、雜湊、AI 分析、掃描 | ~20 req/min（突發 5） |
| **DESTRUCTIVE** | purge、hard-delete、快取清除 | ~12 req/min（突發 3） |
| **WRITE** | 其他 POST/PUT/DELETE | ~120 req/min（突發 30） |
| GET | 讀取 | 無限制 |

收到 429 回應時，檢查 `Retry-After` 標頭。

---

## 相關文件

| 文件 | 位置 |
|----------|----------|
| DB 讀寫分離 | `docs/development/development_docs/SQLITE_READONLY_SEPARATION.md` |
| 錯誤格式標準 | `docs/development/development_docs/ERROR_HANDLING.md` |
| 跨平台問題 | `docs/development/development_docs/CROSS_PLATFORM_ISSUES.md` |
| MCP 除錯工具規格 | `docs/development/development_docs/MCP_DEBUG_TOOLS.md` |
| Quart 遷移記錄 | `docs/development/development_docs/QUART_MIGRATION_DEVLOG.md` |
| QA 交接 | `docs/development/development_docs/QA_HANDOFF.md` |
| 安全檢查清單 | `/security-check` skill |
