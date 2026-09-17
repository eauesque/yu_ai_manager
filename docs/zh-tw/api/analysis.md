# AI Analysis API

AI 驅動的圖片分析、提示詞趨勢分析及伺服器管理的 API。

所有 POST/PUT/DELETE 端點都需要 `X-Requested-With` 標頭（使用 Bearer API Key 時不需要）。

## 速率限制

`/api/analysis/` 下的寫入端點使用 **HEAVY** 層級（約 20 次/分鐘，突發 5 次）。GET 端點無限制。

---

## 設定

### GET /api/analysis/config

取得目前的 AI 分析設定。API Key 以遮罩形式返回。

#### 回應

```json
{
  "engine": "ollama",
  "api_key": "sk-T...xy",
  "model": "claude-sonnet-4-6",
  "ollama_url": "http://localhost:11434",
  "ollama_model": "llava:latest",
  "openai_api_key": "sk-...xy",
  "openai_model": "gpt-4o-mini",
  "openai_compat_url": "http://localhost:8080/v1",
  "openai_compat_api_key": "***...ey",
  "openai_compat_model": "qwen2-vl",
  "hailo_vlm_model": "qwen2-vl-2b-instruct",
  "fallback_local_only": false,
  "language": "ja",
  "is_local": true,
  "has_servers": true,
  "servers": [],
  "active_server": "ollama-main"
}
```

| 欄位 | 型別 | 說明 |
|-------|------|-------------|
| `engine` | string | 目前引擎類型（`claude_api`、`openai`、`ollama`、`openai_compat`、`hailo_vlm`） |
| `api_key` | string | Claude API Key（遮罩） |
| `model` | string | Claude API 模型名稱 |
| `ollama_url` | string | Ollama 伺服器 URL |
| `ollama_model` | string | Ollama 模型名稱 |
| `openai_api_key` | string | OpenAI API Key（遮罩） |
| `openai_model` | string | OpenAI 模型名稱 |
| `openai_compat_url` | string | OpenAI 相容伺服器 URL |
| `openai_compat_api_key` | string | OpenAI 相容 API Key（遮罩） |
| `openai_compat_model` | string | OpenAI 相容模型名稱 |
| `hailo_vlm_model` | string | Hailo VLM 模型名稱 |
| `fallback_local_only` | boolean | 是否僅限本機引擎 |
| `language` | string | 分析結果的語言（`ja`、`en` 等） |
| `is_local` | boolean | 目前引擎是否為本機（免費） |
| `has_servers` | boolean | 是否已設定伺服器登錄 |
| `servers` | array | 伺服器列表（僅當 `has_servers` 為 true 時） |
| `active_server` | string | 作用中伺服器 ID（僅當 `has_servers` 為 true 時） |

### POST /api/analysis/config

儲存 AI 分析設定。遮罩值（包含 `...` 的字串）不會被覆寫。API Key 會自動加密。

#### 速率限制

HEAVY

#### 請求

```json
{
  "engine": "ollama",
  "ollama_url": "http://localhost:11434",
  "ollama_model": "llava:latest",
  "language": "ja"
}
```

| 參數 | 型別 | 必須 | 說明 |
|-----------|------|----------|-------------|
| `engine` | string | 否 | 引擎類型 |
| `api_key` | string | 否 | Claude API Key |
| `model` | string | 否 | Claude API 模型 |
| `ollama_url` | string | 否 | Ollama 伺服器 URL |
| `ollama_model` | string | 否 | Ollama 模型名稱 |
| `openai_api_key` | string | 否 | OpenAI API Key |
| `openai_model` | string | 否 | OpenAI 模型名稱 |
| `openai_compat_url` | string | 否 | OpenAI 相容伺服器 URL |
| `openai_compat_api_key` | string | 否 | OpenAI 相容 API Key |
| `openai_compat_model` | string | 否 | OpenAI 相容模型名稱 |
| `hailo_vlm_model` | string | 否 | Hailo VLM 模型名稱 |
| `fallback_local_only` | boolean | 否 | 僅限本機引擎 |
| `language` | string | 否 | 分析結果的語言 |

#### 回應

```json
{
  "success": true
}
```

---

## 引擎探索

### GET /api/analysis/available-engines

取得已設定且可連線的引擎列表。啟用 `fallback_local_only` 時排除雲端引擎。

#### 回應

```json
{
  "engines": [
    {
      "type": "ollama",
      "label": "Ollama",
      "model": "llava:latest",
      "models": ["llava:latest", "llava:13b", "bakllava:latest"]
    },
    {
      "type": "hailo_vlm",
      "label": "Hailo VLM",
      "model": "qwen2-vl-2b-instruct",
      "models": ["qwen2-vl-2b-instruct"]
    }
  ]
}
```

| 欄位 | 型別 | 說明 |
|-------|------|-------------|
| `engines[].type` | string | 引擎類型識別碼 |
| `engines[].label` | string | 顯示標籤 |
| `engines[].model` | string | 目前設定的模型 |
| `engines[].models` | string[] | 可用模型列表 |

---

## 單檔分析

### POST /api/analysis/analyze/\<file_id\>

使用 AI 引擎分析單一檔案。支援圖片、影片及壓縮檔內的圖片。

#### 速率限制

HEAVY

#### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `file_id` | int | 檔案 ID（路徑參數） |

#### 請求

JSON 主體為選填。省略時使用預設設定。

```json
{
  "mode": "full",
  "engine": "ollama",
  "model": "llava:latest",
  "server_id": "ollama-main"
}
```

| 參數 | 型別 | 必須 | 說明 |
|-----------|------|----------|-------------|
| `mode` | string | 否 | 分析模式。預設 `"full"` |
| `engine` | string | 否 | 覆寫引擎類型 |
| `model` | string | 否 | 覆寫模型名稱 |
| `server_id` | string | 否 | 指定使用的伺服器 ID |

#### 回應 (200)

```json
{
  "success": true,
  "result": {
    "description": "A landscape painting with mountains...",
    "style": "digital art",
    "quality_score": 8,
    "tags": ["landscape", "mountains", "sunset"]
  },
  "engine": "Ollama (llava:latest)"
}
```

#### 錯誤回應

- `400`：引擎未設定 / 指定的引擎無效
- `404`：找不到檔案 / 檔案不存在於磁碟上
- `500`：分析過程中發生錯誤

### GET /api/analysis/result/\<file_id\>

取得檔案的已儲存分析結果。使用多個引擎/模式時返回所有結果。

#### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `file_id` | int | 檔案 ID（路徑參數） |

#### 回應 (200) -- 找到結果

```json
{
  "found": true,
  "result": {
    "engine": "Ollama (llava:latest)",
    "description": "A landscape painting...",
    "style": "digital art",
    "quality_score": 8,
    "analyzed_at": 1709500000
  },
  "results": [
    {
      "engine": "Ollama (llava:latest)",
      "description": "A landscape painting...",
      "style": "digital art",
      "quality_score": 8,
      "analyzed_at": 1709500000
    }
  ]
}
```

| 欄位 | 型別 | 說明 |
|-------|------|-------------|
| `found` | boolean | 是否存在分析結果 |
| `result` | object | 最新的分析結果（向後相容用） |
| `results` | array | 所有分析結果的陣列 |

#### 回應 (200) -- 無結果

```json
{
  "found": false
}
```

---

## 批次分析

### POST /api/analysis/batch

對未分析的檔案啟動批次 AI 分析工作。在背景執行。

#### 速率限制

HEAVY

#### 請求

```json
{
  "limit": 10,
  "scan_root": "",
  "file_ids": [],
  "server_ids": ["ollama-main", "openai-compat"]
}
```

| 參數 | 型別 | 必須 | 說明 |
|-----------|------|----------|-------------|
| `limit` | int | 否 | 分析的最大檔案數。預設 10。雲端引擎上限為 10。本機引擎設為 0 表示全部 |
| `scan_root` | string | 否 | 限制目標為特定掃描根目錄 |
| `file_ids` | int[] | 否 | 直接指定要分析的檔案 ID |
| `server_ids` | string[] | 否 | 使用的伺服器 ID。多個伺服器可啟用平行分析 |

#### 回應 (200)

```json
{
  "started": true,
  "count": 10,
  "parallel": false
}
```

| 欄位 | 型別 | 說明 |
|-------|------|-------------|
| `started` | boolean | 工作是否已開始 |
| `count` | int | 要分析的檔案數 |
| `parallel` | boolean | 是否平行執行（多個 `server_ids`） |
| `worker` | boolean | 若透過推論工作者分派則為 true |
| `subprocess` | boolean | 若以子行程執行（Hailo VLM）則為 true |

#### 錯誤回應

- `400`：沒有要分析的檔案
- `409`：AI 分析工作已在執行中

### POST /api/analysis/batch/cancel

取消正在執行的批次 AI 分析工作。

#### 速率限制

HEAVY

#### 請求

不需要主體。

#### 回應 (200)

```json
{
  "status": "cancelling",
  "message": "AI analysis cancel requested"
}
```

#### 錯誤回應

- `404`：沒有正在執行的 AI 分析工作

---

## 提示詞趨勢分析

### POST /api/analysis/trends

對最近 50 個提示詞執行趨勢分析。結果會自動儲存至歷史記錄。

#### 速率限制

HEAVY

#### 請求

不需要主體。

#### 回應 (200)

```json
{
  "success": true,
  "result": {
    "summary": "Recent prompts focus on landscape and character art...",
    "top_themes": ["landscape", "character", "fantasy"],
    "trend_direction": "increasing variety"
  }
}
```

#### 錯誤回應

- `400`：API Key 未設定（使用雲端引擎時）
- `500`：趨勢分析過程中發生錯誤

### GET /api/analysis/trends/history

取得提示詞趨勢分析歷史。按最新排序。最多保留 50 筆。

#### 參數

| 參數 | 型別 | 預設 | 說明 |
|-----------|------|---------|-------------|
| `limit` | int | 20 | 取得的筆數（最多 50） |
| `offset` | int | 0 | 位移量 |

#### 回應

```json
{
  "items": [
    {
      "id": 5,
      "engine": "ollama",
      "analyzed_at": 1709500000,
      "prompt_count": 50,
      "result": {
        "summary": "Recent prompts focus on...",
        "top_themes": ["landscape", "character"]
      }
    }
  ]
}
```

| 欄位 | 型別 | 說明 |
|-------|------|-------------|
| `items[].id` | int | 歷史記錄 ID |
| `items[].engine` | string | 使用的引擎類型 |
| `items[].analyzed_at` | int | 分析的 UNIX 時間戳 |
| `items[].prompt_count` | int | 分析的提示詞數量 |
| `items[].result` | object | 趨勢分析結果 |

### DELETE /api/analysis/trends/history/\<history_id\>

刪除單筆趨勢分析歷史記錄。

#### 速率限制

HEAVY

#### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `history_id` | int | 歷史記錄 ID（路徑參數） |

#### 回應

```json
{
  "deleted": true
}
```

#### 錯誤回應

- `404`：找不到歷史記錄

---

## 統計資訊

### GET /api/analysis/stats

取得 AI 分析統計資訊。

#### 回應

```json
{
  "total_analyzed": 150,
  "total_files": 1200,
  "styles": [
    { "style": "digital art", "count": 45 },
    { "style": "anime", "count": 30 }
  ],
  "quality_distribution": [
    { "tier": "excellent", "count": 20, "avg_score": 8.5 },
    { "tier": "good", "count": 60, "avg_score": 6.8 },
    { "tier": "average", "count": 50, "avg_score": 4.9 },
    { "tier": "low", "count": 20, "avg_score": 2.3 }
  ]
}
```

| 欄位 | 型別 | 說明 |
|-------|------|-------------|
| `total_analyzed` | int | 已分析的檔案數 |
| `total_files` | int | 總檔案數（不含已刪除） |
| `styles` | array | 風格分布（前 10 名） |
| `styles[].style` | string | 風格名稱 |
| `styles[].count` | int | 檔案數 |
| `quality_distribution` | array | 品質分數分布 |
| `quality_distribution[].tier` | string | 品質等級（`excellent` >= 8、`good` >= 6、`average` >= 4、`low` < 4） |
| `quality_distribution[].count` | int | 檔案數 |
| `quality_distribution[].avg_score` | float | 平均分數 |

---

## Ollama 連線

### GET /api/analysis/ollama/models

連線至已設定的 Ollama 伺服器並列出可用模型。

#### 回應

```json
{
  "available": true,
  "models": [
    { "name": "llava:latest", "size": 4700000000 }
  ]
}
```

#### 錯誤回應

- `400`：Ollama URL 無效

### POST /api/analysis/ollama/test

測試與指定 URL 的 Ollama 伺服器的連線。

#### 速率限制

HEAVY

#### 請求

```json
{
  "ollama_url": "http://localhost:11434"
}
```

| 參數 | 型別 | 必須 | 說明 |
|-----------|------|----------|-------------|
| `ollama_url` | string | 是 | 要測試的 Ollama 伺服器 URL |

#### 回應

```json
{
  "available": true,
  "models": [
    { "name": "llava:latest", "size": 4700000000 }
  ]
}
```

#### 錯誤回應

- `400`：URL 為空 / URL 無效

---

## OpenAI 相容伺服器連線

### GET /api/analysis/openai-compat/models

連線至已設定的 OpenAI 相容伺服器並列出可用模型。

#### 回應

```json
{
  "available": true,
  "models": [
    { "id": "qwen2-vl-7b-instruct" }
  ]
}
```

#### 錯誤回應

- `400`：URL 未設定 / URL 無效

### POST /api/analysis/openai-compat/test

測試與指定 URL 的 OpenAI 相容伺服器的連線。

#### 速率限制

HEAVY

#### 請求

```json
{
  "url": "http://localhost:8080/v1",
  "api_key": "optional-key"
}
```

| 參數 | 型別 | 必須 | 說明 |
|-----------|------|----------|-------------|
| `url` | string | 是 | 要測試的 URL |
| `api_key` | string | 否 | API Key（如需要） |

#### 回應

```json
{
  "available": true,
  "models": [
    { "id": "qwen2-vl-7b-instruct" }
  ]
}
```

#### 錯誤回應

- `400`：URL 為空 / URL 無效

---

## AI 伺服器登錄

註冊和管理多個 AI 伺服器，支援基於優先順序的回退和平行分析。

### GET /api/analysis/servers

列出所有已註冊的伺服器及其狀態。API Key 會被遮罩。

#### 回應

```json
{
  "servers": [
    {
      "id": "ollama-main",
      "name": "Ollama (llava:latest)",
      "type": "ollama",
      "priority": 10,
      "enabled": true,
      "config": {
        "base_url": "http://localhost:11434",
        "model": "llava:latest"
      },
      "is_active": true,
      "status": "unknown"
    }
  ]
}
```

| 欄位 | 型別 | 說明 |
|-------|------|-------------|
| `servers[].id` | string | 伺服器 ID（不可變更） |
| `servers[].name` | string | 顯示名稱 |
| `servers[].type` | string | 引擎類型（`claude_api`、`openai`、`ollama`、`openai_compat`、`hailo_vlm`） |
| `servers[].priority` | int | 優先順序（數值越低優先順序越高） |
| `servers[].enabled` | boolean | 啟用/停用 |
| `servers[].config` | object | 引擎特定設定 |
| `servers[].is_active` | boolean | 是否為目前作用中的伺服器 |
| `servers[].status` | string | 連線狀態（列表檢視中始終為 `"unknown"`） |

### POST /api/analysis/servers

註冊新伺服器。第一個伺服器會自動設為作用中。

#### 速率限制

HEAVY

#### 請求

```json
{
  "name": "Local Ollama",
  "type": "ollama",
  "config": {
    "base_url": "http://localhost:11434",
    "model": "llava:latest"
  }
}
```

| 參數 | 型別 | 必須 | 說明 |
|-----------|------|----------|-------------|
| `name` | string | 是 | 伺服器名稱 |
| `type` | string | 是 | 引擎類型 |
| `config` | object | 是 | 引擎特定設定 |
| `priority` | int | 否 | 優先順序 |
| `enabled` | boolean | 否 | 啟用/停用。預設 true |

#### 回應 (201)

```json
{
  "success": true,
  "server": {
    "id": "local-ollama",
    "name": "Local Ollama",
    "type": "ollama",
    "priority": 10,
    "enabled": true,
    "config": { "base_url": "http://localhost:11434", "model": "llava:latest" }
  }
}
```

#### 錯誤回應

- `400`：驗證錯誤 / 已達伺服器上限

### PUT /api/analysis/servers/\<server_id\>

更新伺服器設定。`id` 欄位無法變更。

#### 速率限制

HEAVY

#### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `server_id` | string | 伺服器 ID（路徑參數） |

#### 請求

```json
{
  "name": "Updated Name",
  "type": "ollama",
  "priority": 20,
  "enabled": true,
  "config": { "base_url": "http://192.168.1.100:11434", "model": "llava:13b" }
}
```

所有欄位均為選填。僅更新指定的欄位。

#### 回應

```json
{
  "success": true,
  "server": { "id": "ollama-main", "name": "Updated Name", "..." : "..." }
}
```

#### 錯誤回應

- `400`：類型無效 / 找不到伺服器

### DELETE /api/analysis/servers/\<server_id\>

刪除伺服器。若刪除的是作用中的伺服器，會自動切換至下一個最高優先順序的伺服器。

#### 速率限制

HEAVY

#### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `server_id` | string | 伺服器 ID（路徑參數） |

#### 回應

```json
{
  "success": true
}
```

#### 錯誤回應

- `400`：找不到伺服器

### POST /api/analysis/servers/\<server_id\>/activate

切換作用中的伺服器。

#### 速率限制

HEAVY

#### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `server_id` | string | 伺服器 ID（路徑參數） |

#### 回應

```json
{
  "success": true,
  "active": "ollama-main"
}
```

#### 錯誤回應

- `400`：找不到伺服器

### POST /api/analysis/servers/\<server_id\>/test

對伺服器執行連線測試。同時測量回應時間。

#### 速率限制

HEAVY

#### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `server_id` | string | 伺服器 ID（路徑參數） |

#### 回應

```json
{
  "success": true,
  "available": true,
  "elapsed_ms": 45,
  "server": {
    "id": "ollama-main",
    "name": "Local Ollama",
    "type": "ollama",
    "config": { "..." : "..." }
  }
}
```

| 欄位 | 型別 | 說明 |
|-------|------|-------------|
| `available` | boolean | 伺服器是否可連線 |
| `elapsed_ms` | int | 連線測試回應時間（毫秒） |
| `server` | object | 伺服器資訊 |

#### 錯誤回應

- `400`：找不到伺服器

### PUT /api/analysis/servers/reorder

批次更新伺服器優先順序。

#### 速率限制

HEAVY

#### 請求

```json
{
  "server_ids": ["ollama-main", "openai-compat", "claude-api"]
}
```

| 參數 | 型別 | 必須 | 說明 |
|-----------|------|----------|-------------|
| `server_ids` | string[] | 是 | 伺服器 ID 陣列。指定的順序成為新的優先順序 |

#### 回應

```json
{
  "success": true
}
```

#### 錯誤回應

- `400`：`server_ids` 不是陣列

### POST /api/analysis/servers/migrate

從舊版 `ai_analysis` 設定自動遷移至新的伺服器登錄格式。若已存在伺服器則失敗。

#### 速率限制

HEAVY

#### 請求

不需要主體。

#### 回應

```json
{
  "success": true,
  "servers": [
    { "id": "ollama", "name": "Ollama (llava:latest)", "type": "ollama", "..." : "..." }
  ],
  "migrated": 3
}
```

| 欄位 | 型別 | 說明 |
|-------|------|-------------|
| `servers` | array | 遷移建立的伺服器 |
| `migrated` | int | 建立的伺服器數量 |

#### 錯誤回應

- `400`：`ai_servers` 已存在
