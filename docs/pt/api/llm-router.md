# API do LLM Router

O LLM Router no YU AI Manager fornece uma interface unificada para múltiplos backends LLM locais (Ollama, hailo-ollama, etc.) através dos protocolos Anthropic Messages API e OpenAI Chat Completions API.

URL Base: `http://localhost:5000/v1`

## Endpoints

### POST /v1/messages

API Anthropic Messages compatível. Conecte via `ANTHROPIC_BASE_URL=http://localhost:5000/v1` do Claude Code / Claude Desktop.

Requisição:
```json
{
  "model": "local-coder-big",
  "messages": [{"role": "user", "content": "..."}],
  "system": "...",
  "max_tokens": 1024,
  "stream": false
}
```

Resposta: Formato Anthropic Messages.

### POST /v1/chat/completions

API OpenAI Chat Completions compatível. Para clientes compatíveis com OpenAI como Continue / Aider.

### GET /v1/models

Retorna uma lista combinada de todos os modelos e aliases de todos os backends no formato OpenAI `/v1/models`. O campo `yu_metadata` contém informações proprietárias como context_window / size_b / backend_status.

### GET /v1/router/health

Retorna o status do Router e um resumo de backend. Para diagnósticos.

### POST /v1/router/refresh

Use `{"backend": "ollama-mac"}` para atualizar um único backend, ou envie um corpo vazio para forçar re-descoberta de todos os backends.

### POST /v1/router/estimate

Estimativa de contagem de tokens (aproximação tiktoken cl100k).

### GET /v1/router/capabilities/{target}

Metadados de modelo curados, incluindo good_at / weak_at / notes.

## Autenticação

`config.json` `llm_router.auth.mode`:

| modo | Comportamento |
|---|---|
| `loopback` (padrão) | Permite acesso não autenticado apenas de 127.0.0.1 / ::1 |
| `api_key` | Valida header `x-api-key` ou `Authorization: Bearer` |
| `none` | Sem autenticação |

Veja `docs/pt/llm-router/setup.md` para detalhes.
