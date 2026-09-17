# LLM Router API

YU AI Manager 的 LLM Router 將多個本機 LLM 後端（Ollama、hailo-ollama 等）透過 Anthropic Messages API 及 OpenAI Chat Completions API 兩種協定提供統一介面。

基礎 URL：`http://localhost:5000/v1`

## 端點

### POST /v1/messages

Anthropic Messages API 相容。可透過 Claude Code / Claude Desktop 的 `ANTHROPIC_BASE_URL=http://localhost:5000/v1` 連線。

請求：
```json
{
  "model": "local-coder-big",
  "messages": [{"role": "user", "content": "..."}],
  "system": "...",
  "max_tokens": 1024,
  "stream": false
}
```

回應：Anthropic Messages 格式。

### POST /v1/chat/completions

OpenAI Chat Completions API 相容。供 Continue / Aider 等 OpenAI 相容用戶端使用。

### GET /v1/models

以 OpenAI `/v1/models` 格式回傳所有後端的全部模型 + alias 列表。`yu_metadata` 欄位包含 context_window / size_b / backend_status 等專有資訊。

### GET /v1/router/health

Router 本身的狀態與後端摘要。供診斷使用。

### POST /v1/router/refresh

`{"backend": "ollama-mac"}` 可重新探測單一後端，無 body 時強制重新探測所有後端。

### POST /v1/router/estimate

Token 數量估算（tiktoken cl100k 近似值）。

### GET /v1/router/capabilities/{target}

模型的 good_at / weak_at / notes 等精選中繼資料。

## 認證

`config.json` 的 `llm_router.auth.mode`：

| mode | 行為 |
|---|---|
| `loopback`（預設） | 僅允許 127.0.0.1 / ::1 免認證存取 |
| `api_key` | 驗證 `x-api-key` 或 `Authorization: Bearer` 標頭 |
| `none` | 不認證 |

詳情請參閱 `docs/zh-tw/llm-router/setup.md`。
