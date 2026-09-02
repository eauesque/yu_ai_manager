# API di inferenza distribuita

REST API per il registro del server di inferenza distribuita. Distribuisce i carichi di lavoro di indicizzazione semantica CLIP su più nodi utilizzando una strategia di coda condivisa.

## Endpoint

### GET /api/inference-servers

Restituisce l'elenco dei server registrati e la modalità di invio corrente.

**Risposta:**

```json
{
  "status": "ok",
  "mode": "single",
  "servers": [
    {
      "id": 1,
      "name": "Hailo Worker 1",
      "endpoint_url": "http://192.168.1.10:9090",
      "inference_types": ["clip"],
      "priority": 50,
      "enabled": true,
      "timeout": 30
    }
  ]
}
```

- `mode`: `"single"` | `"parallel"` | `"idle_first"`
- `servers`: array di oggetti di configurazione del server

---

### POST /api/inference-servers

Registra un nuovo server di inferenza.

**Corpo della richiesta:**

| Campo | Tipo | Obbligatorio | Predefinito | Descrizione |
|---|---|---|---|---|
| `name` | string | ✓ | — | Nome visualizzato |
| `endpoint_url` | string | ✓ | — | URL base worker |
| `inference_types` | string[] | — | `["clip"]` | Tipi di inferenza supportati |
| `priority` | int | — | `50` | Priorità (valore più basso = priorità più alta) |
| `bearer_token` | string | — | — | Token di autenticazione |
| `timeout` | int | — | `30` | Timeout della richiesta in secondi |

**Risposta:**

```json
{
  "status": "ok",
  "server": { ... }
}
```

---

### PUT /api/inference-servers/{server_id}

Aggiorna la configurazione di un server esistente. Accetta un corpo parziale con gli stessi campi di POST.

---

### DELETE /api/inference-servers/{server_id}

Rimuovi un server dal registro.

**Risposta:**

```json
{ "status": "ok" }
```

---

### POST /api/inference-servers/{server_id}/test

Esegui un controllo dello stato di integrità rispetto al server specificato.

**Risposta:**

```json
{
  "status": "ok",
  "server_id": 1,
  "healthy": true,
  "latency_ms": 12.5
}
```

---

### GET /api/inference-servers/health

Esegui controlli dello stato di integrità su tutti i server abilitati contemporaneamente.

**Risposta:**

```json
{
  "status": "ok",
  "results": [
    { "server_id": 1, "healthy": true, "latency_ms": 12.5 },
    { "server_id": 2, "healthy": false, "error": "Connection refused" }
  ]
}
```

---

### POST /api/inference-servers/mode

Imposta la modalità di invio.

**Corpo della richiesta:**

| Campo | Tipo | Obbligatorio | Descrizione |
|---|---|---|---|
| `mode` | string | ✓ | `"single"` \| `"parallel"` \| `"idle_first"` |

**Risposta:**

```json
{ "status": "ok", "mode": "parallel" }
```

---

## Modalità di invio

| Modalità | Descrizione |
|---|---|
| `single` | Utilizza solo il server con la priorità più alta (valore di priorità più basso) |
| `parallel` | Distribuisci il lavoro su tutti i server abilitati utilizzando una coda condivisa |
| `idle_first` | Controllo dello stato di integrità per primo, quindi distribuisci tra server reattivi solo |

## Indicizzazione semantica distribuita

Aggiungi `distributed: true` al corpo della richiesta `POST /api/index/start` (estensione di ricerca semantica) per abilitare l'indicizzazione distribuita utilizzando i server worker registrati.

```json
{
  "batch_size": 32,
  "distributed": true
}
```

## Configurazione del server Worker

```bash
python deploy/hailo_tagger_server.py --port 9090
```

Endpoint supportati:

| Percorso | Descrizione |
|---|---|
| `GET /health` | Controllo dello stato di integrità |
| `POST /tag` | Inferenza WD-Tagger |
| `POST /clip-encode` | Codifica vettore CLIP |

## Strumenti MCP

| Strumento | Descrizione |
|---|---|
| `inference-servers-list` | Elenca server e ottieni la modalità corrente |
| `inference-server-add` | Registra un nuovo server |
| `inference-server-update` | Aggiorna la configurazione del server |
| `inference-server-remove` | Rimuovi un server |
| `inference-server-health` | Esegui controlli dello stato di integrità |
| `inference-dispatch-mode-set` | Imposta la modalità di invio |
