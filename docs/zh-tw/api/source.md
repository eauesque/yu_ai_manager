# Source Code Browsing API

唯讀瀏覽專案原始碼的 API。
設計目的是讓 MCP 工具和外部 AI 代理可以安全地檢視和搜尋程式碼庫。

## 安全模型

三層防禦確保安全性：

### 1. 路徑正規化（遍歷防護）

- 所有路徑使用 `os.path.realpath()` 正規化，並透過前綴比對與專案根目錄進行驗證。
- 阻擋 `../../etc/passwd` 或 `../../../Windows/System32` 等遍歷攻擊。
- 同時偵測並拒絕空位元組注入（`\x00`）。

### 2. 副檔名白名單

允許讀取的檔案副檔名：

| 分類 | 副檔名 |
|----------|-----------|
| Python | `.py` |
| TypeScript / JavaScript | `.ts`, `.js`, `.mjs`, `.tsx`, `.jsx` |
| Web | `.html`, `.css`, `.scss` |
| 設定 | `.json`, `.yaml`, `.yml`, `.toml`, `.cfg`, `.ini` |
| 文件 | `.md`, `.txt`, `.rst` |
| 腳本 | `.sh`, `.bat`, `.cmd`, `.ps1` |
| 其他 | `.sql`, `.gitignore`, `.gitattributes`, `.editorconfig` |

以下無副檔名的檔案被特別允許：`Dockerfile`、`Makefile`、`Procfile`、`VERSION`、`LICENSE`、`CHANGELOG`、`TODO`

### 3. 敏感檔案黑名單

符合以下模式的檔案將被拒絕：

| 模式 | 原因 |
|---------|--------|
| `config.json`、`config_*.json` | PIN、API Key 等認證資料 |
| `*.env`、`.env.*` | 環境變數（密鑰） |
| `secret.salt`、`*.key`、`*.pem`、`*.cert` | 加密金鑰和憑證 |
| `credentials*`、`*token*`、`*secret*` | 認證資料 |
| `*.db`、`*.sqlite*` | 資料庫檔案 |
| `pnpm-lock.yaml`、`package-lock.json` 等 | 鎖定檔案（大檔案） |
| 圖片、影片、字型、模型檔案 | 二進位檔案 |

### 被封鎖的目錄

`.git`、`__pycache__`、`node_modules`、`venv`、`dist`、`data`、`backups`、`screenshots`、`reports`、`src-tauri`

### 讀取限制

| 項目 | 限制 |
|------|-------|
| 檔案大小 | 1 MB |
| 每次讀取行數 | 2,000 |
| 樹遍歷深度 | 6 |
| 搜尋結果 | 50 |

---

## 端點

### GET /api/source/tree

取得目錄樹。

#### 參數

| 參數 | 類型 | 預設值 | 說明 |
|-----------|------|---------|-------------|
| `path` | string | `""`（根目錄） | 相對路徑 |
| `depth` | int | `3` | 遍歷深度（1-6） |

#### 回應

```json
{
  "ok": true,
  "root": ".",
  "depth": 3,
  "entries": [
    {
      "name": "core",
      "type": "dir",
      "path": "core",
      "children": [
        {
          "name": "source_core",
          "type": "dir",
          "path": "core/source_core",
          "children": [
            {
              "name": "source_browser.py",
              "type": "file",
              "path": "core/source_core/source_browser.py",
              "size": 8234
            }
          ]
        }
      ]
    },
    {
      "name": "web_ui.py",
      "type": "file",
      "path": "web_ui.py",
      "size": 3456
    }
  ]
}
```

- 目錄在前，檔案在後（按名稱排序）。
- `size` 以位元組為單位（僅檔案）。
- 達到指定 `depth` 後 `children` 將被省略。

---

### GET /api/source/read

讀取含行號的檔案內容。

#### 參數

| 參數 | 類型 | 預設值 | 說明 |
|-----------|------|---------|-------------|
| `path` | string | —（必填） | 相對檔案路徑 |
| `offset` | int | `0` | 起始行（從 0 開始） |
| `limit` | int | `2000` | 最大行數 |

#### 回應

```json
{
  "ok": true,
  "path": "core/source_core/source_browser.py",
  "total_lines": 250,
  "offset": 0,
  "limit": 2000,
  "content": "    1\t\"\"\"Source code browser...\n    2\t\n    3\timport os\n..."
}
```

- `content` 使用 `{行號}\t{行內容}` 格式。
- 使用 `offset` + `limit` 對長檔案進行分頁讀取。

#### 錯誤範例

```json
{
  "ok": false,
  "error": "This file is not eligible for reading"
}
```

```json
{
  "ok": false,
  "error": "Access outside the project root is prohibited"
}
```

---

### GET /api/source/search

在原始碼中搜尋文字。

#### 參數

| 參數 | 類型 | 預設值 | 說明 |
|-----------|------|---------|-------------|
| `q` | string | —（必填） | 搜尋文字（至少 2 個字元） |
| `glob` | string | `""`（所有檔案） | 檔名篩選（如 `*.py`） |
| `limit` | int | `30` | 最大結果數（1-50） |

#### 回應

```json
{
  "ok": true,
  "query": "def source_tree",
  "glob": "*.py",
  "total": 2,
  "results": [
    {
      "file": "core/source_core/source_browser.py",
      "line": 120,
      "text": "def source_tree("
    },
    {
      "file": "routes/source_api.py",
      "line": 15,
      "text": "    result = source_tree(rel_path, depth_int)"
    }
  ]
}
```

- 搜尋不區分大小寫。
- `text` 最多截斷為 200 個字元。

---

## MCP 工具

| 工具 | 說明 | 主要參數 |
|------|-------------|----------------|
| `source_tree` | 顯示目錄樹 | `path`: str = '', `depth`: int = 3 |
| `source_read` | 讀取檔案內容 | `path`: str（必填）, `offset`: int = 0, `limit`: int = 2000 |
| `source_search` | 按文字搜尋原始碼 | `query`: str（必填）, `glob`: str = '', `limit`: int = 30 |

### MCP 使用範例

```
# 檢視專案結構
source_tree(path="", depth=2)

# 讀取特定檔案
source_read(path="core/source_core/source_browser.py")

# 在程式碼庫中搜尋
source_search(query="def register_blueprints", glob="*.py")
```

### 範圍與速率限制

- **Scope Fence**：在 `read_only` 範圍內可用（所有預設中均允許）
- **Budget Tracker**：`read` 類別（無速率限制）
- **HITL Gate**：等級 0（無需核准）

---

## 實作檔案

| 檔案 | 職責 |
|------|------|
| `core/source_core/source_browser.py` | 安全層 + 業務邏輯 |
| `routes/source_api.py` | Flask API 端點（Blueprint） |
| `mcp_server/source_tools.py` | MCP 工具註冊 |
