# API: /api/llm_router (Admin)

Endpoint admin per operazioni di gestione del LLM Router. Protetto dall'autenticazione standard della sessione WebUI (PIN/session), e completamente separato dalla superficie compatibile con OpenAI `/v1/*`.

> **Nota**: Questi sono endpoint admin e sono distinti dagli endpoint di inferenza come `/v1/chat/completions`.

---

## Formato di risposta comune

Tutti gli endpoint utilizzano il wrapper `api_result`. Al successo, il corpo è annidato sotto la chiave `data`.

```json
{
  "status": "ok",
  "data": { ... }
}
```

In caso di errore:

```json
{
  "status": "error",
  "error": "Error description"
}
```

---

## GET /api/llm_router/status

Un'istantanea per il rendering dell'intera dashboard in una singola richiesta. Restituisce tutte le informazioni del backend e la mappa degli alias.

### Richiesta

```
GET /api/llm_router/status
```

Nessun parametro.

### Risposta `200 OK`

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

### Descrizioni dei campi

**`router`**

| Campo | Tipo | Descrizione |
|---|---|---|
| `version` | string | Versione dello schema del router (attualmente `"1.0.0"`) |
| `alias_count` | int | Numero di alias definiti |

**`backends[]`**

| Campo | Tipo | Descrizione |
|---|---|---|
| `alias` | string | Identificatore backend univoco |
| `base_url` | string | URL base dell'endpoint compatibile con OpenAI |
| `source` | string | `"static"` (file di configurazione) o `"mdns"` (scoperto automaticamente) |
| `status` | string | `"ready"` / `"unreachable"` / `"unknown"` |
| `slo_state` | string \| null | `"vision_idle"` / `"vision_active"` / `"unknown"` / `null` |
| `disabled` | bool | `true` se escluso dal routing |
| `model_count` | int | Numero di modelli esposti |
| `models[]` | array | Elenco modelli (`name`, `context_window`, `size_b`) |
| `last_seen` | string \| null | Ultimo controllo di connettività riuscito (ISO 8601) |
| `last_error` | string \| null | Messaggio di errore più recente |

**`aliases`**

Una mappa di nomi alias logici a ID modelli fisici (`backend-alias/model-name`).

---

## POST /api/llm_router/refresh

Forza un sondaggio su tutti i backend o su un backend specificato, aggiornando `status` e l'elenco dei modelli.

### Richiesta

**Per aggiornare tutti i backend (nessun corpo):**

```
POST /api/llm_router/refresh
Content-Type: application/json

{}
```

Un corpo vuoto senza intestazione Content-Type è accettato anche.

**Per aggiornare solo un backend specifico:**

```json
{
  "alias": "ollama-mac"
}
```

### Risposta `200 OK`

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

L'array `refreshed` contiene solo risultati di aggiornamento leggeri (usa `/status` per i dettagli completi).

### Errore `404 Not Found`

Quando è specificato un `alias` ma non esiste:

```json
{
  "status": "error",
  "error": "unknown backend: nonexistent-alias"
}
```

### Note

- I sondaggi vengono eseguiti in modo sincrono (la risposta viene restituita dopo il completamento)
- I sondaggi vengono eseguiti anche per i backend con `disabled: true` (lo stato viene comunque aggiornato)
- I backend scoperti da mDNS sono inclusi

---

## POST /api/llm_router/backends/`<alias>`/disable

Disabilita il backend specificato. I backend disabilitati vengono esclusi dal routing e lo stato viene persistito in `data/llm_router_state.json`.

### Richiesta

```
POST /api/llm_router/backends/ollama-mac/disable
```

Nessun corpo richiesto.

### Risposta `200 OK`

```json
{
  "status": "ok",
  "data": {
    "alias": "ollama-mac",
    "disabled": true
  }
}
```

### Errore `404 Not Found`

```json
{
  "status": "error",
  "error": "unknown backend: nonexistent-alias"
}
```

### Errore `500 Internal Server Error`

Quando la persistenza su disco non riesce (errore di autorizzazione, disco pieno, ecc.). Lo stato in memoria viene ripristinato.

```json
{
  "status": "error",
  "error": "failed to persist disabled state"
}
```

### Meccanismo di persistenza

1. Imposta il flag `disabled` su `true` nel catalogo in memoria
2. Scrivi atomicamente in `data/llm_router_state.json` (tramite file `.tmp` e `os.replace`)
3. Se la scrittura non riesce, il passaggio 1 viene ripristinato e viene restituito un `500`

Lo stato disabilitato viene preservato tra i riavvii dell'applicazione. Se un backend scoperto da mDNS era disabilitato prima dell'avvio, lo stato disabilitato viene applicato automaticamente dopo la scoperta.

---

## POST /api/llm_router/backends/`<alias>`/enable

Abilita il backend specificato. L'opposto di `disable`.

### Richiesta

```
POST /api/llm_router/backends/ollama-mac/enable
```

Nessun corpo richiesto.

### Risposta `200 OK`

```json
{
  "status": "ok",
  "data": {
    "alias": "ollama-mac",
    "disabled": false
  }
}
```

### Errori

Stesso dell'endpoint `disable` (`404` / `500`). Persistito con `disabled: false`.

---

## Riepilogo endpoint

| Metodo | Percorso | Descrizione |
|---|---|---|
| `GET` | `/api/llm_router/status` | Ottieni un'istantanea di tutti i backend e gli alias |
| `POST` | `/api/llm_router/refresh` | Forza il sondaggio su tutti i backend o su uno individuale |
| `POST` | `/api/llm_router/backends/<alias>/disable` | Disabilita un backend (persistito) |
| `POST` | `/api/llm_router/backends/<alias>/enable` | Abilita un backend (persistito) |

## Documentazione correlata

- [Guida WebUI LLM Router](../llm-router/webui.md)
- [Configurazione LLM Router](../llm-router/setup.md)
