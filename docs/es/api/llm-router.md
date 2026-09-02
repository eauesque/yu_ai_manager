# API de Router LLM

El Router LLM en YU AI Manager proporciona una interfaz unificada para múltiples backends LLM locales (Ollama, hailo-ollama, etc.) a través de los protocolos de API Anthropic Messages y OpenAI Chat Completions.

URL Base: `http://localhost:5000/v1`

## Endpoints

### POST /v1/messages

Compatible con API de Mensajes de Anthropic. Conectar a través de `ANTHROPIC_BASE_URL=http://localhost:5000/v1` desde Claude Code / Claude Desktop.

Solicitud:
```json
{
  "model": "local-coder-big",
  "messages": [{"role": "user", "content": "..."}],
  "system": "...",
  "max_tokens": 1024,
  "stream": false
}
```

Respuesta: Formato de Mensajes de Anthropic.

### POST /v1/chat/completions

Compatible con API de Chat Completions de OpenAI. Para clientes compatibles con OpenAI como Continue / Aider.

### GET /v1/models

Devuelve una lista combinada de todos los modelos y alias de todos los backends en el formato OpenAI `/v1/models`. El campo `yu_metadata` contiene información propia como context_window / size_b / backend_status.

### GET /v1/router/health

Devuelve el estado del propio Router y un resumen del backend. Para diagnósticos.

### POST /v1/router/refresh

Use `{"backend": "ollama-mac"}` para actualizar un solo backend, u envíe un cuerpo vacío para forzar el redescubrimiento de todos los backends.

### POST /v1/router/estimate

Estimación de conteo de tokens (aproximación tiktoken cl100k).

### GET /v1/router/capabilities/{target}

Metadatos de modelo curados incluyendo good_at / weak_at / notes.

## Autenticación

`config.json` `llm_router.auth.mode`:

| modo | Comportamiento |
|---|---|
| `loopback` (predeterminado) | Permite acceso no autenticado solo desde 127.0.0.1 / ::1 |
| `api_key` | Valida encabezado `x-api-key` o `Authorization: Bearer` |
| `none` | Sin autenticación |

Consulte `docs/en/llm-router/setup.md` para más detalles.
