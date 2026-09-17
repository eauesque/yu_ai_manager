# API LLM Router

L'LLM Router in YU AI Manager fornisce un'interfaccia unificata per più backend LLM locali (Ollama, hailo-ollama, ecc.) attraverso i protocolli API Anthropic Messages e OpenAI Chat Completions.

URL base: `http://localhost:5000/v1`

## Endpoint

### POST /v1/messages

API Messages Anthropic compatibile. Collegati tramite `ANTHROPIC_BASE_URL=http://localhost:5000/v1` da Claude Code / Claude Desktop.

Richiesta:
```json
{
  "model": "local-coder-big",
  "messages": [{"role": "user", "content": "..."}],
  "system": "...",
  "max_tokens": 1024,
  "stream": false
}
```

Risposta: Formato Anthropic Messages.

### POST /v1/chat/completions

API OpenAI Chat Completions compatibile. Per client compatibili con OpenAI come Continue / Aider.

### GET /v1/models

Restituisce un elenco combinato di tutti i modelli e gli alias da tutti i backend nel formato OpenAI `/v1/models`. Il campo `yu_metadata` contiene informazioni proprietarie come context_window / size_b / backend_status.

### GET /v1/router/health

Restituisce lo stato del Router stesso e un riepilogo del backend. Per la diagnostica.

### POST /v1/router/refresh

Usa `{"backend": "ollama-mac"}` per aggiornare un singolo backend, o invia un corpo vuoto per forzare la riscoperta di tutti i backend.

### POST /v1/router/estimate

Stima del numero di token (approssimazione tiktoken cl100k).

### GET /v1/router/capabilities/{target}

Metadati del modello curati inclusi good_at / weak_at / note.

## Autenticazione

`config.json` `llm_router.auth.mode`:

| mode | Comportamento |
|---|---|
| `loopback` (predefinito) | Consente l'accesso non autenticato solo da 127.0.0.1 / ::1 |
| `api_key` | Convalida l'intestazione `x-api-key` o `Authorization: Bearer` |
| `none` | Nessuna autenticazione |

Vedere `docs/en/llm-router/setup.md` per i dettagli.
