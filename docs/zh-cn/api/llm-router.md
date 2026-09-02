# LLM Router API

YU AI Manager 的 LLM Router 将多个本地 LLM 后端（Ollama、hailo-ollama 等）通过 Anthropic Messages API 和 OpenAI Chat Completions API 两种协议统一接口化。

基础 URL: `http://localhost:5000/v1`

## 端点

### POST /v1/messages

Anthropic Messages API 兼容。可通过 Claude Code / Claude Desktop 的 `ANTHROPIC_BASE_URL=http://localhost:5000/v1` 连接。

请求:
```json
{
  "model": "local-coder-big",
  "messages": [{"role": "user", "content": "..."}],
  "system": "...",
  "max_tokens": 1024,
  "stream": false
}
```

响应: Anthropic Messages 格式。

### POST /v1/chat/completions

OpenAI Chat Completions API 兼容。用于 Continue / Aider 等 OpenAI 兼容客户端。

### GET /v1/models

以 OpenAI `/v1/models` 格式返回所有后端的所有模型 + alias 列表。`yu_metadata` 字段包含 context_window / size_b / backend_status 等专有信息。

### GET /v1/router/health

Router 本身的状态和后端摘要。用于诊断。

### POST /v1/router/refresh

`{"backend": "ollama-mac"}` 指定单个后端，无请求体时对所有后端强制重新执行 discovery。

### POST /v1/router/estimate

Token 数量估算（tiktoken cl100k 近似）。

### GET /v1/router/capabilities/{target}

模型的 good_at / weak_at / notes 等精选元数据。

## 认证

`config.json` 的 `llm_router.auth.mode`:

| 模式 | 行为 |
|---|---|
| `loopback`（默认） | 仅允许 127.0.0.1 / ::1 无认证访问 |
| `api_key` | 验证 `x-api-key` 或 `Authorization: Bearer` 头 |
| `none` | 无认证 |

详情参见 `docs/zh-cn/llm-router/setup.md`。
