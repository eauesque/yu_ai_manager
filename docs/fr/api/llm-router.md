# API LLM Router

Le LLM Router dans YU AI Manager fournit une interface unifiée pour plusieurs backends LLM locaux (Ollama, hailo-ollama, etc.) via les protocoles API Anthropic Messages et OpenAI Chat Completions.

URL de base : `http://localhost:5000/v1`

## Points d'accès

### POST /v1/messages

API Anthropic Messages compatible. Connectez via `ANTHROPIC_BASE_URL=http://localhost:5000/v1` depuis Claude Code / Claude Desktop.

Requête :
```json
{
  "model": "local-coder-big",
  "messages": [{"role": "user", "content": "..."}],
  "system": "...",
  "max_tokens": 1024,
  "stream": false
}
```

Réponse : format Anthropic Messages.

### POST /v1/chat/completions

API OpenAI Chat Completions compatible. Pour les clients compatibles OpenAI tels que Continue / Aider.

### GET /v1/models

Retourne une liste combinée de tous les modèles et alias de tous les backends au format OpenAI `/v1/models`. Le champ `yu_metadata` contient des informations propriétaires telles que context_window / size_b / backend_status.

### GET /v1/router/health

Retourne le statut du Router lui-même et un résumé du backend. Pour les diagnostics.

### POST /v1/router/refresh

Utilisez `{"backend": "ollama-mac"}` pour actualiser un seul backend, ou envoyez un corps vide pour forcer la re-découverte de tous les backends.

### POST /v1/router/estimate

Estimation du nombre de tokens (approximation tiktoken cl100k).

### GET /v1/router/capabilities/{target}

Métadonnées de modèle curées incluant good_at / weak_at / notes.

## Authentification

`config.json` `llm_router.auth.mode` :

| mode | Comportement |
|---|---|
| `loopback` (par défaut) | Permet l'accès non authentifié uniquement depuis 127.0.0.1 / ::1 |
| `api_key` | Valide l'en-tête `x-api-key` ou `Authorization: Bearer` |
| `none` | Aucune authentification |

Voir `docs/en/llm-router/setup.md` pour les détails.
