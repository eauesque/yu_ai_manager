# LLM Router API

The LLM Router in YU AI Manager provides a unified interface for multiple local LLM backends (Ollama, hailo-ollama, etc.) through both the Anthropic Messages API and OpenAI Chat Completions API protocols.

Base URL: `http://localhost:5000/v1`

## Endpoints

### POST /v1/messages

Anthropic Messages API compatible. Connect via `ANTHROPIC_BASE_URL=http://localhost:5000/v1` from Claude Code / Claude Desktop.

Request:
```json
{
  "model": "local-coder-big",
  "messages": [{"role": "user", "content": "..."}],
  "system": "...",
  "max_tokens": 1024,
  "stream": false
}
```

Response: Anthropic Messages format.

### POST /v1/chat/completions

OpenAI Chat Completions API compatible. For OpenAI-compatible clients such as Continue / Aider.

### GET /v1/models

Returns a combined list of all models and aliases from all backends in the OpenAI `/v1/models` format. The `yu_metadata` field contains proprietary information such as context_window / size_b / backend_status.

### GET /v1/router/health

Returns the Router's own status and a backend summary. For diagnostics.

### POST /v1/router/refresh

Use `{"backend": "ollama-mac"}` to refresh a single backend, or send an empty body to force re-discovery of all backends.

### POST /v1/router/estimate

Token count estimation (tiktoken cl100k approximation).

### GET /v1/router/capabilities/{target}

Curated model metadata including good_at / weak_at / notes.

## Authentication

`config.json` `llm_router.auth.mode`:

| mode | Behavior |
|---|---|
| `loopback` (default) | Allows unauthenticated access only from 127.0.0.1 / ::1 |
| `api_key` | Validates `x-api-key` or `Authorization: Bearer` header |
| `none` | No authentication |

See `docs/en/llm-router/setup.md` for details.
