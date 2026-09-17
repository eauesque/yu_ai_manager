# API: /api/llm_router (Admin)

Endpoints de admin para operações de gerenciamento do LLM Router. Protegidos pela autenticação de sessão WebUI padrão (PIN/session), e completamente separados da superfície `/v1/*` compatível com OpenAI.

> **Nota**: Estes são endpoints de admin e são distintos de endpoints de inferência como `/v1/chat/completions`.

---

## Formato de Resposta Comum

Todos os endpoints usam o wrapper `api_result`. Em caso de sucesso, o corpo é aninhado sob a chave `data`.

```json
{
  "status": "ok",
  "data": { ... }
}
```

Em caso de erro:

```json
{
  "status": "error",
  "error": "Descrição do erro"
}
```

---

## GET /api/llm_router/status

Um snapshot para renderizar todo o dashboard em uma única requisição. Retorna todas as informações de backend e o mapa de alias.

### Requisição

```
GET /api/llm_router/status
```

Sem parâmetros.

### Resposta `200 OK`

```json
{
  "status": "ok",
  "data": {
    "router": {
      "version": "1.0.0",
      "alias_count": 2
    },
    "backends": [
      {
        "alias": "ollama-mac",
        "base_url": "http://192.168.1.10:11434",
        "source": "static",
        "status": "ready",
        "slo_state": null,
        "disabled": false,
        "model_count": 3,
        "models": [
          {
            "name": "qwen2.5:7b",
            "context_window": 32768,
            "size_b": 7.6
          },
          {
            "name": "llama3.2:3b",
            "context_window": 128000,
            "size_b": 3.2
          }
        ],
        "last_seen": "2026-04-09T12:34:56.789123",
        "last_error": null
      },
      {
        "alias": "mdns-pi5-hailo",
        "base_url": "http://192.168.1.20:8080",
        "source": "mdns",
        "status": "unreachable",
        "slo_state": "unknown",
        "disabled": false,
        "model_count": 0,
        "models": [],
        "last_seen": null,
        "last_error": "Connection refused"
      }
    ],
    "aliases": {
      "default-llm": "ollama-mac/qwen2.5:7b",
      "fast-chat": "ollama-mac/llama3.2:3b"
    }
  }
}
```

### Descrições de Campo

**`router`**

| Campo | Tipo | Descrição |
|---|---|---|
| `version` | string | Versão de schema do Router (atualmente `"1.0.0"`) |
| `alias_count` | int | Número de aliases definidos |

**`backends[]`**

| Campo | Tipo | Descrição |
|---|---|---|
| `alias` | string | Identificador único de backend |
| `base_url` | string | URL base do endpoint compatível com OpenAI |
| `source` | string | `"static"` (arquivo de config) ou `"mdns"` (auto-descoberto) |
| `status` | string | `"ready"` / `"unreachable"` / `"unknown"` |
| `slo_state` | string \| null | `"vision_idle"` / `"vision_active"` / `"unknown"` / `null` |
| `disabled` | bool | `true` se excluído do roteamento |
| `model_count` | int | Número de modelos expostos |
| `models[]` | array | Lista de modelos (`name`, `context_window`, `size_b`) |
| `last_seen` | string \| null | Última verificação de conectividade bem-sucedida (ISO 8601) |
| `last_error` | string \| null | Mensagem de último erro |

**`aliases`**

Um mapa de nomes de alias lógico para IDs de modelo físico (`backend-alias/model-name`).

---

## POST /api/llm_router/refresh

Força uma sonda em todos os backends ou em um backend específico, atualizando `status` e a lista de modelos.

### Requisição

**Para atualizar todos os backends (sem corpo):**

```
POST /api/llm_router/refresh
Content-Type: application/json

{}
```

Um corpo vazio sem um header Content-Type também é aceito.

**Para atualizar apenas um backend específico:**

```json
{
  "alias": "ollama-mac"
}
```

### Resposta `200 OK`

```json
{
  "status": "ok",
  "data": {
    "refreshed": [
      {
        "alias": "ollama-mac",
        "status": "ready",
        "model_count": 3,
        "disabled": false,
        "last_error": null
      },
      {
        "alias": "mdns-pi5-hailo",
        "status": "unreachable",
        "model_count": 0,
        "disabled": false,
        "last_error": "Connection refused"
      }
    ]
  }
}
```

O array `refreshed` contém apenas resultados de atualização leve (use `/status` para detalhes completos).

### Erro `404 Not Found`

Quando um `alias` é especificado mas não existe:

```json
{
  "status": "error",
  "error": "unknown backend: nonexistent-alias"
}
```

### Notas

- Sondas são executadas de forma síncrona (a resposta é retornada após a conclusão)
- Sondas também são executadas para backends com `disabled: true` (status ainda é atualizado)
- Backends descobertos por mDNS são incluídos

---

## POST /api/llm_router/backends/`<alias>`/disable

Desabilita o backend especificado. Backends desabilitados são excluídos do roteamento e o estado é persistido para `data/llm_router_state.json`.

### Requisição

```
POST /api/llm_router/backends/ollama-mac/disable
```

Nenhum corpo obrigatório.

### Resposta `200 OK`

```json
{
  "status": "ok",
  "data": {
    "alias": "ollama-mac",
    "disabled": true
  }
}
```

### Erro `404 Not Found`

```json
{
  "status": "error",
  "error": "unknown backend: nonexistent-alias"
}
```

### Erro `500 Internal Server Error`

Quando a persistência em disco falha (erro de permissão, disco cheio, etc.). O estado em memória é revertido.

```json
{
  "status": "error",
  "error": "failed to persist disabled state"
}
```

### Mecanismo de Persistência

1. Defina a flag `disabled` para `true` no catálogo em memória
2. Escreva atomicamente em `data/llm_router_state.json` (via arquivo `.tmp` e `os.replace`)
3. Se a escrita falhar, a etapa 1 é revertida e um `500` é retornado

O estado desabilitado é preservado entre reinicializações da aplicação. Se um backend descoberto por mDNS foi desabilitado antes da inicialização, o estado desabilitado é aplicado automaticamente após a descoberta.

---

## POST /api/llm_router/backends/`<alias>`/enable

Habilita o backend especificado. O inverso de `disable`.

### Requisição

```
POST /api/llm_router/backends/ollama-mac/enable
```

Nenhum corpo obrigatório.

### Resposta `200 OK`

```json
{
  "status": "ok",
  "data": {
    "alias": "ollama-mac",
    "disabled": false
  }
}
```

### Erros

Mesmo que o endpoint `disable` (`404` / `500`). Persistido com `disabled: false`.

---

## Resumo de Endpoint

| Método | Caminho | Descrição |
|---|---|---|
| `GET` | `/api/llm_router/status` | Obter um snapshot de todos os backends e aliases |
| `POST` | `/api/llm_router/refresh` | Forçar sonda em todos ou backends individuais |
| `POST` | `/api/llm_router/backends/<alias>/disable` | Desabilitar um backend (persistido) |
| `POST` | `/api/llm_router/backends/<alias>/enable` | Habilitar um backend (persistido) |

## Documentação Relacionada

- [Guia LLM Router WebUI](../llm-router/webui.md)
- [Configuração do LLM Router](../llm-router/setup.md)
