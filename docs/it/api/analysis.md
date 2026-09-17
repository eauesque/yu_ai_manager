# API di Analisi AI

API per l'analisi delle immagini tramite AI, l'analisi delle tendenze dei prompt e la gestione dei server.

Tutti gli endpoint POST/PUT/DELETE richiedono l'header `X-Requested-With` (non necessario quando si utilizza Bearer API Key).

## Rate Limit

Gli endpoint di scrittura sotto `/api/analysis/` utilizzano il livello **HEAVY** (~20 req/min, burst 5). Gli endpoint GET non hanno limiti.

---

## Configurazione

### GET /api/analysis/config

Ottieni la configurazione corrente dell'analisi AI. Le API key vengono restituite mascherate.

#### Risposta

```json
{
  "engine": "ollama",
  "api_key": "sk-T...xy",
  "model": "claude-sonnet-4-6",
  "ollama_url": "http://localhost:11434",
  "ollama_model": "llava:latest",
  "openai_api_key": "sk-...xy",
  "openai_model": "gpt-4o-mini",
  "openai_compat_url": "http://localhost:8080/v1",
  "openai_compat_api_key": "***...ey",
  "openai_compat_model": "qwen2-vl",
  "hailo_vlm_model": "qwen2-vl-2b-instruct",
  "fallback_local_only": false,
  "language": "ja",
  "is_local": true,
  "has_servers": true,
  "servers": [],
  "active_server": "ollama-main"
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `engine` | string | Tipo di engine corrente (`claude_api`, `openai`, `ollama`, `openai_compat`, `hailo_vlm`) |
| `api_key` | string | Claude API key (mascherata) |
| `model` | string | Nome del modello Claude API |
| `ollama_url` | string | URL del server Ollama |
| `ollama_model` | string | Nome del modello Ollama |
| `openai_api_key` | string | OpenAI API key (mascherata) |
| `openai_model` | string | Nome del modello OpenAI |
| `openai_compat_url` | string | URL del server compatibile OpenAI |
| `openai_compat_api_key` | string | API key compatibile OpenAI (mascherata) |
| `openai_compat_model` | string | Nome del modello compatibile OpenAI |
| `hailo_vlm_model` | string | Nome del modello Hailo VLM |
| `fallback_local_only` | boolean | Se limitare agli engine locali soltanto |
| `language` | string | Lingua per i risultati dell'analisi (`ja`, `en`, ecc.) |
| `is_local` | boolean | Se l'engine corrente è locale (gratuito) |
| `has_servers` | boolean | Se il registro dei server è configurato |
| `servers` | array | Elenco dei server (solo quando `has_servers` è true) |
| `active_server` | string | ID del server attivo (solo quando `has_servers` è true) |

### POST /api/analysis/config

Salva la configurazione dell'analisi AI. I valori mascherati (stringhe contenenti `...`) non vengono sovrascritti. Le API key vengono crittografate automaticamente.

#### Rate Limit

HEAVY

#### Richiesta

```json
{
  "engine": "ollama",
  "ollama_url": "http://localhost:11434",
  "ollama_model": "llava:latest",
  "language": "ja"
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|--------------|-------------|
| `engine` | string | No | Tipo di engine |
| `api_key` | string | No | Claude API key |
| `model` | string | No | Modello Claude API |
| `ollama_url` | string | No | URL del server Ollama |
| `ollama_model` | string | No | Nome del modello Ollama |
| `openai_api_key` | string | No | OpenAI API key |
| `openai_model` | string | No | Nome del modello OpenAI |
| `openai_compat_url` | string | No | URL del server compatibile OpenAI |
| `openai_compat_api_key` | string | No | API key compatibile OpenAI |
| `openai_compat_model` | string | No | Nome del modello compatibile OpenAI |
| `hailo_vlm_model` | string | No | Nome del modello Hailo VLM |
| `fallback_local_only` | boolean | No | Limita agli engine locali soltanto |
| `language` | string | No | Lingua per i risultati dell'analisi |

#### Risposta

```json
{
  "success": true
}
```

---

## Rilevamento Engine

### GET /api/analysis/available-engines

Ottieni un elenco degli engine configurati e raggiungibili. Gli engine cloud vengono esclusi quando `fallback_local_only` è abilitato.

#### Risposta

```json
{
  "engines": [
    {
      "type": "ollama",
      "label": "Ollama",
      "model": "llava:latest",
      "models": ["llava:latest", "llava:13b", "bakllava:latest"]
    },
    {
      "type": "hailo_vlm",
      "label": "Hailo VLM",
      "model": "qwen2-vl-2b-instruct",
      "models": ["qwen2-vl-2b-instruct"]
    }
  ]
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `engines[].type` | string | Identificatore del tipo di engine |
| `engines[].label` | string | Etichetta di visualizzazione |
| `engines[].model` | string | Modello attualmente configurato |
| `engines[].models` | string[] | Elenco dei modelli disponibili |

---

## Analisi di un Singolo File

### POST /api/analysis/analyze/\<file_id\>

Analizza un singolo file con un engine AI. Supporta immagini, video e immagini all'interno di archivi.

#### Rate Limit

HEAVY

#### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `file_id` | int | ID del file (parametro percorso) |

#### Richiesta

Il body JSON è opzionale. Se omesso, vengono usate le impostazioni predefinite.

```json
{
  "mode": "full",
  "engine": "ollama",
  "model": "llava:latest",
  "server_id": "ollama-main"
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|--------------|-------------|
| `mode` | string | No | Modalità di analisi. Default `"full"` |
| `engine` | string | No | Sostituisce il tipo di engine |
| `model` | string | No | Sostituisce il nome del modello |
| `server_id` | string | No | Specifica l'ID del server da utilizzare |

#### Risposta (200)

```json
{
  "success": true,
  "result": {
    "description": "A landscape painting with mountains...",
    "style": "digital art",
    "quality_score": 8,
    "tags": ["landscape", "mountains", "sunset"]
  },
  "engine": "Ollama (llava:latest)"
}
```

#### Risposte di Errore

- `400`: Engine non configurato / engine specificato non valido
- `404`: File non trovato / il file non esiste su disco
- `500`: Errore durante l'analisi

### GET /api/analysis/result/\<file_id\>

Recupera i risultati dell'analisi memorizzati per un file. Restituisce tutti i risultati quando sono stati utilizzati più engine/modalità.

#### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `file_id` | int | ID del file (parametro percorso) |

#### Risposta (200) -- Risultati Trovati

```json
{
  "found": true,
  "result": {
    "engine": "Ollama (llava:latest)",
    "description": "A landscape painting...",
    "style": "digital art",
    "quality_score": 8,
    "analyzed_at": 1709500000
  },
  "results": [
    {
      "engine": "Ollama (llava:latest)",
      "description": "A landscape painting...",
      "style": "digital art",
      "quality_score": 8,
      "analyzed_at": 1709500000
    }
  ]
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `found` | boolean | Se esistono risultati di analisi |
| `result` | object | Risultato dell'analisi più recente (compatibilità con versioni precedenti) |
| `results` | array | Array di tutti i risultati dell'analisi |

#### Risposta (200) -- Nessun Risultato

```json
{
  "found": false
}
```

---

## Analisi in Batch

### POST /api/analysis/batch

Avvia un job di analisi AI in batch sui file non ancora analizzati. Viene eseguito in background.

#### Rate Limit

HEAVY

#### Richiesta

```json
{
  "limit": 10,
  "scan_root": "",
  "file_ids": [],
  "server_ids": ["ollama-main", "openai-compat"]
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|--------------|-------------|
| `limit` | int | No | Numero massimo di file da analizzare. Default 10. Limite massimo 10 per gli engine cloud. 0 significa tutti i file per gli engine locali |
| `scan_root` | string | No | Limita i target a uno specifico scan root |
| `file_ids` | int[] | No | Specifica direttamente gli ID dei file da analizzare |
| `server_ids` | string[] | No | ID dei server da utilizzare. Più server abilitano l'analisi in parallelo |

#### Risposta (200)

```json
{
  "started": true,
  "count": 10,
  "parallel": false
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `started` | boolean | Se il job è stato avviato |
| `count` | int | Numero di file da analizzare |
| `parallel` | boolean | Se in esecuzione in parallelo (più `server_ids`) |
| `worker` | boolean | True se inviato tramite inference worker |
| `subprocess` | boolean | True se in esecuzione in subprocess (Hailo VLM) |

#### Risposte di Errore

- `400`: Nessun file da analizzare
- `409`: Job di analisi AI già in esecuzione

### POST /api/analysis/batch/cancel

Annulla un job di analisi AI in batch in esecuzione.

#### Rate Limit

HEAVY

#### Richiesta

Nessun body richiesto.

#### Risposta (200)

```json
{
  "status": "cancelling",
  "message": "AI analysis cancel requested"
}
```

#### Risposte di Errore

- `404`: Nessun job di analisi AI in esecuzione

---

## Analisi delle Tendenze dei Prompt

### POST /api/analysis/trends

Esegui l'analisi delle tendenze sugli ultimi 50 prompt. I risultati vengono automaticamente salvati nella cronologia.

#### Rate Limit

HEAVY

#### Richiesta

Nessun body richiesto.

#### Risposta (200)

```json
{
  "success": true,
  "result": {
    "summary": "Recent prompts focus on landscape and character art...",
    "top_themes": ["landscape", "character", "fantasy"],
    "trend_direction": "increasing variety"
  }
}
```

#### Risposte di Errore

- `400`: API key non configurata (quando si usano engine cloud)
- `500`: Errore durante l'analisi delle tendenze

### GET /api/analysis/trends/history

Ottieni la cronologia dell'analisi delle tendenze dei prompt. Ordinata dalla più recente. Vengono conservate al massimo 50 voci.

#### Parametri

| Parametro | Tipo | Default | Descrizione |
|-----------|------|---------|-------------|
| `limit` | int | 20 | Numero di voci da recuperare (max 50) |
| `offset` | int | 0 | Offset |

#### Risposta

```json
{
  "items": [
    {
      "id": 5,
      "engine": "ollama",
      "analyzed_at": 1709500000,
      "prompt_count": 50,
      "result": {
        "summary": "Recent prompts focus on...",
        "top_themes": ["landscape", "character"]
      }
    }
  ]
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `items[].id` | int | ID della voce nella cronologia |
| `items[].engine` | string | Tipo di engine utilizzato |
| `items[].analyzed_at` | int | Timestamp UNIX dell'analisi |
| `items[].prompt_count` | int | Numero di prompt analizzati |
| `items[].result` | object | Risultato dell'analisi delle tendenze |

### DELETE /api/analysis/trends/history/\<history_id\>

Elimina una singola voce dalla cronologia dell'analisi delle tendenze.

#### Rate Limit

HEAVY

#### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `history_id` | int | ID della voce nella cronologia (parametro percorso) |

#### Risposta

```json
{
  "deleted": true
}
```

#### Risposte di Errore

- `404`: Voce della cronologia non trovata

---

## Statistiche

### GET /api/analysis/stats

Ottieni le statistiche dell'analisi AI.

#### Risposta

```json
{
  "total_analyzed": 150,
  "total_files": 1200,
  "styles": [
    { "style": "digital art", "count": 45 },
    { "style": "anime", "count": 30 }
  ],
  "quality_distribution": [
    { "tier": "excellent", "count": 20, "avg_score": 8.5 },
    { "tier": "good", "count": 60, "avg_score": 6.8 },
    { "tier": "average", "count": 50, "avg_score": 4.9 },
    { "tier": "low", "count": 20, "avg_score": 2.3 }
  ]
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `total_analyzed` | int | Numero di file analizzati |
| `total_files` | int | Numero totale di file (esclusi i cancellati) |
| `styles` | array | Distribuzione degli stili (top 10) |
| `styles[].style` | string | Nome dello stile |
| `styles[].count` | int | Numero di file |
| `quality_distribution` | array | Distribuzione del punteggio di qualità |
| `quality_distribution[].tier` | string | Livello di qualità (`excellent` >= 8, `good` >= 6, `average` >= 4, `low` < 4) |
| `quality_distribution[].count` | int | Numero di file |
| `quality_distribution[].avg_score` | float | Punteggio medio |

---

## Connessione Ollama

### GET /api/analysis/ollama/models

Connettiti al server Ollama configurato ed elenca i modelli disponibili.

#### Risposta

```json
{
  "available": true,
  "models": [
    { "name": "llava:latest", "size": 4700000000 }
  ]
}
```

#### Risposte di Errore

- `400`: URL Ollama non valido

### POST /api/analysis/ollama/test

Testa la connessione a un server Ollama all'URL specificato.

#### Rate Limit

HEAVY

#### Richiesta

```json
{
  "ollama_url": "http://localhost:11434"
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|--------------|-------------|
| `ollama_url` | string | Sì | URL del server Ollama da testare |

#### Risposta

```json
{
  "available": true,
  "models": [
    { "name": "llava:latest", "size": 4700000000 }
  ]
}
```

#### Risposte di Errore

- `400`: URL vuoto / URL non valido

---

## Connessione Server Compatibile OpenAI

### GET /api/analysis/openai-compat/models

Connettiti al server compatibile OpenAI configurato ed elenca i modelli disponibili.

#### Risposta

```json
{
  "available": true,
  "models": [
    { "id": "qwen2-vl-7b-instruct" }
  ]
}
```

#### Risposte di Errore

- `400`: URL non configurato / URL non valido

### POST /api/analysis/openai-compat/test

Testa la connessione a un server compatibile OpenAI all'URL specificato.

#### Rate Limit

HEAVY

#### Richiesta

```json
{
  "url": "http://localhost:8080/v1",
  "api_key": "optional-key"
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|--------------|-------------|
| `url` | string | Sì | URL da testare |
| `api_key` | string | No | API key (se richiesta) |

#### Risposta

```json
{
  "available": true,
  "models": [
    { "id": "qwen2-vl-7b-instruct" }
  ]
}
```

#### Risposte di Errore

- `400`: URL vuoto / URL non valido

---

## Registro Server AI

Registra e gestisci più server AI con fallback basato su priorità e analisi in parallelo.

### GET /api/analysis/servers

Elenca tutti i server registrati con lo stato. Le API key sono mascherate.

#### Risposta

```json
{
  "servers": [
    {
      "id": "ollama-main",
      "name": "Ollama (llava:latest)",
      "type": "ollama",
      "priority": 10,
      "enabled": true,
      "config": {
        "base_url": "http://localhost:11434",
        "model": "llava:latest"
      },
      "is_active": true,
      "status": "unknown"
    }
  ]
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `servers[].id` | string | ID del server (immutabile) |
| `servers[].name` | string | Nome di visualizzazione |
| `servers[].type` | string | Tipo di engine (`claude_api`, `openai`, `ollama`, `openai_compat`, `hailo_vlm`) |
| `servers[].priority` | int | Priorità (valore minore = priorità maggiore) |
| `servers[].enabled` | boolean | Abilitato/disabilitato |
| `servers[].config` | object | Configurazione specifica dell'engine |
| `servers[].is_active` | boolean | Se questo è il server attualmente attivo |
| `servers[].status` | string | Stato della connessione (sempre `"unknown"` nella vista elenco) |

### POST /api/analysis/servers

Registra un nuovo server. Il primo server viene impostato automaticamente come attivo.

#### Rate Limit

HEAVY

#### Richiesta

```json
{
  "name": "Local Ollama",
  "type": "ollama",
  "config": {
    "base_url": "http://localhost:11434",
    "model": "llava:latest"
  }
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|--------------|-------------|
| `name` | string | Sì | Nome del server |
| `type` | string | Sì | Tipo di engine |
| `config` | object | Sì | Configurazione specifica dell'engine |
| `priority` | int | No | Priorità |
| `enabled` | boolean | No | Abilitato/disabilitato. Default true |

#### Risposta (201)

```json
{
  "success": true,
  "server": {
    "id": "local-ollama",
    "name": "Local Ollama",
    "type": "ollama",
    "priority": 10,
    "enabled": true,
    "config": { "base_url": "http://localhost:11434", "model": "llava:latest" }
  }
}
```

#### Risposte di Errore

- `400`: Errore di validazione / limite server raggiunto

### PUT /api/analysis/servers/\<server_id\>

Aggiorna le impostazioni di un server. Il campo `id` non può essere modificato.

#### Rate Limit

HEAVY

#### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `server_id` | string | ID del server (parametro percorso) |

#### Richiesta

```json
{
  "name": "Updated Name",
  "type": "ollama",
  "priority": 20,
  "enabled": true,
  "config": { "base_url": "http://192.168.1.100:11434", "model": "llava:13b" }
}
```

Tutti i campi sono opzionali. Vengono aggiornati solo i campi specificati.

#### Risposta

```json
{
  "success": true,
  "server": { "id": "ollama-main", "name": "Updated Name", "..." : "..." }
}
```

#### Risposte di Errore

- `400`: Tipo non valido / server non trovato

### DELETE /api/analysis/servers/\<server_id\>

Elimina un server. Se il server attivo viene eliminato, il server con la priorità successiva più alta diventa automaticamente attivo.

#### Rate Limit

HEAVY

#### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `server_id` | string | ID del server (parametro percorso) |

#### Risposta

```json
{
  "success": true
}
```

#### Risposte di Errore

- `400`: Server non trovato

### POST /api/analysis/servers/\<server_id\>/activate

Cambia il server attivo.

#### Rate Limit

HEAVY

#### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `server_id` | string | ID del server (parametro percorso) |

#### Risposta

```json
{
  "success": true,
  "active": "ollama-main"
}
```

#### Risposte di Errore

- `400`: Server non trovato

### POST /api/analysis/servers/\<server_id\>/test

Esegui un test di connettività su un server. Viene misurato anche il tempo di risposta.

#### Rate Limit

HEAVY

#### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `server_id` | string | ID del server (parametro percorso) |

#### Risposta

```json
{
  "success": true,
  "available": true,
  "elapsed_ms": 45,
  "server": {
    "id": "ollama-main",
    "name": "Local Ollama",
    "type": "ollama",
    "config": { "..." : "..." }
  }
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `available` | boolean | Se il server è raggiungibile |
| `elapsed_ms` | int | Tempo di risposta del test di connessione in millisecondi |
| `server` | object | Informazioni sul server |

#### Risposte di Errore

- `400`: Server non trovato

### PUT /api/analysis/servers/reorder

Aggiorna in blocco le priorità dei server.

#### Rate Limit

HEAVY

#### Richiesta

```json
{
  "server_ids": ["ollama-main", "openai-compat", "claude-api"]
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|--------------|-------------|
| `server_ids` | string[] | Sì | Array degli ID dei server. L'ordine specificato diventa il nuovo ordine di priorità |

#### Risposta

```json
{
  "success": true
}
```

#### Risposte di Errore

- `400`: `server_ids` non è un array

### POST /api/analysis/servers/migrate

Migra automaticamente dalla configurazione legacy `ai_analysis` al nuovo formato del registro server. Fallisce se i server esistono già.

#### Rate Limit

HEAVY

#### Richiesta

Nessun body richiesto.

#### Risposta

```json
{
  "success": true,
  "servers": [
    { "id": "ollama", "name": "Ollama (llava:latest)", "type": "ollama", "..." : "..." }
  ],
  "migrated": 3
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `servers` | array | Server creati dalla migrazione |
| `migrated` | int | Numero di server creati |

#### Risposte di Errore

- `400`: `ai_servers` esiste già
