# LLM Router API

Der LLM Router in YU AI Manager bietet eine einheitliche Schnittstelle für mehrere lokale LLM-Backends (Ollama, hailo-ollama, usw.) durch sowohl die Anthropic Messages API als auch die OpenAI Chat Completions API Protokolle.

Basis-URL: `http://localhost:5000/v1`

## Endpunkte

### POST /v1/messages

Anthropic Messages API kompatibel. Verbinden Sie sich über `ANTHROPIC_BASE_URL=http://localhost:5000/v1` von Claude Code / Claude Desktop.

Anfrage:
```json
{
  "model": "local-coder-big",
  "messages": [{"role": "user", "content": "..."}],
  "system": "...",
  "max_tokens": 1024,
  "stream": false
}
```

Antwort: Anthropic Messages Format.

### POST /v1/chat/completions

OpenAI Chat Completions API kompatibel. Für OpenAI-kompatible Clients wie Continue / Aider.

### GET /v1/models

Gibt eine kombinierte Liste aller Modelle und Aliases von allen Backends im OpenAI `/v1/models`-Format zurück. Das Feld `yu_metadata` enthält proprietäre Informationen wie context_window / size_b / backend_status.

### GET /v1/router/health

Gibt den Status des Routers selbst und eine Backend-Zusammenfassung zurück. Für Diagnosen.

### POST /v1/router/refresh

Verwenden Sie `{"backend": "ollama-mac"}`, um ein einzelnes Backend zu aktualisieren, oder senden Sie einen leeren Körper, um die Neuermittlung aller Backends zu erzwingen.

### POST /v1/router/estimate

Token-Count-Schätzung (tiktoken cl100k Approximation).

### GET /v1/router/capabilities/{target}

Kuratierte Modell-Metadaten einschließlich good_at / weak_at / notes.

## Authentifizierung

`config.json` `llm_router.auth.mode`:

| mode | Verhalten |
|---|---|
| `loopback` (Standard) | Erlaubt unauthentifizierten Zugriff nur von 127.0.0.1 / ::1 |
| `api_key` | Validiert Header `x-api-key` oder `Authorization: Bearer` |
| `none` | Keine Authentifizierung |

Siehe `docs/en/llm-router/setup.md` für Details.
