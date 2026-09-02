# API Gateway di Sicurezza dell'Agente

API per la gestione dei controlli di sicurezza degli agenti AI. Fornisce funzionalità di Kill Switch, Circuit Breaker, Budget, Action Journal, Approval Gate, Scope Fence, Auto-Approve, Tool Classification, Undo, Anomaly Detection, e Audit Bureau.

Tutti gli endpoint POST/DELETE richiedono l'header `X-Requested-With` (ad eccezione di quando si utilizza Bearer API Key).

---

## Kill Switch

### POST /api/agent/kill

Attiva il Kill Switch per interrompere immediatamente tutte le operazioni degli agenti.

#### Rate Limit

WRITE

#### Richiesta

```json
{
  "reason": "Manual kill via API"
}
```

| Parametro | Tipo | Richiesto | Descrizione |
|-----------|------|----------|-------------|
| `reason` | string | No | Motivo dell'arresto. Predefinito: `"Manual kill via API"` |

#### Risposta

```json
{
  "ok": true,
  "status": {
    "killed": true,
    "reason": "Manual kill via API",
    "killed_at": "2026-03-22T12:00:00"
  }
}
```

### POST /api/agent/resume

Disattiva il Kill Switch per riprendere le operazioni degli agenti.

#### Rate Limit

WRITE

#### Richiesta

Nessuna (corpo vuoto)

#### Risposta

```json
{
  "ok": true,
  "status": {
    "killed": false,
    "reason": "",
    "killed_at": ""
  }
}
```

### GET /api/agent/status

Ottieni lo stato unificato di Kill Switch, Circuit Breaker, e Budget.

#### Parametri

Nessuno

#### Risposta

```json
{
  "kill_switch": {
    "killed": false,
    "reason": "",
    "killed_at": ""
  },
  "circuit_breaker": {
    "enabled": true,
    "state": "closed",
    "failure_count": 0,
    "threshold": 5
  },
  "budget": {
    "session_id": "abc123",
    "used": 10,
    "limit": 100,
    "remaining": 90
  },
  "killed": false,
  "reason": "",
  "killed_at": ""
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `kill_switch` | object | Stato dettagliato del Kill Switch |
| `circuit_breaker` | object | Stato dettagliato del Circuit Breaker. Restituisce `{"enabled": false, "state": "unknown"}` in caso di errore |
| `budget` | object | Stato dettagliato del Budget. Restituisce un oggetto vuoto in caso di errore |
| `killed` | boolean | Flag del Kill Switch attivo (top-level per compatibilità all'indietro) |
| `reason` | string | Motivo del Kill Switch (compatibilità all'indietro) |
| `killed_at` | string | Ora di attivazione del Kill Switch (compatibilità all'indietro) |

---

## Circuit Breaker

### GET /api/agent/circuit-breaker

Ottieni lo stato del Circuit Breaker.

#### Parametri

Nessuno

#### Risposta

```json
{
  "enabled": true,
  "state": "closed",
  "failure_count": 0,
  "threshold": 5
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `enabled` | boolean | Se il Circuit Breaker è abilitato |
| `state` | string | Stato: `"closed"` (normale), `"open"` (attivato), `"half_open"` (probing) |
| `failure_count` | int | Conteggio dei fallimenti consecutivi |
| `threshold` | int | Soglia del conteggio dei fallimenti per attivare open |

### POST /api/agent/circuit-breaker/reset

Reimposta il Circuit Breaker allo stato closed.

#### Rate Limit

WRITE

#### Richiesta

Nessuna (corpo vuoto)

#### Risposta

```json
{
  "ok": true,
  "status": {
    "enabled": true,
    "state": "closed",
    "failure_count": 0,
    "threshold": 5
  }
}
```

---

## Budget

### GET /api/agent/budget

Ottieni il budget rimanente per la sessione attuale.

#### Parametri

Nessuno

#### Risposta

```json
{
  "session_id": "abc123",
  "used": 10,
  "limit": 100,
  "remaining": 90
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `session_id` | string | ID della sessione |
| `used` | int | Numero di azioni consumate |
| `limit` | int | Massimo di azioni consentite |
| `remaining` | int | Azioni rimanenti |

### POST /api/agent/budget/reset

Reimposta il contatore del budget.

#### Rate Limit

WRITE

#### Richiesta

Nessuna (corpo vuoto)

#### Risposta

```json
{
  "ok": true,
  "status": {
    "session_id": "abc123",
    "used": 0,
    "limit": 100,
    "remaining": 100
  }
}
```

---

## Action Journal

### GET /api/agent/journal

Ricerca nell'Action Journal. Restituisce la cronologia delle azioni eseguite dagli agenti.

#### Parametri

| Parametro | Tipo | Richiesto | Descrizione |
|-----------|------|----------|-------------|
| `tool_name` | string | No | Filtra per nome dello strumento |
| `status` | string | No | Filtra per stato |
| `session_id` | string | No | Filtra per ID della sessione |
| `limit` | int | No | Max risultati (predefinito: 50, max: 200) |
| `offset` | int | No | Offset (predefinito: 0) |

#### Risposta

```json
{
  "entries": [
    {
      "id": 1,
      "tool_name": "add_tags",
      "session_id": "abc123",
      "status": "completed",
      "params": {"file_id": 42, "tags": ["landscape"]},
      "result": {"ok": true},
      "created_at": "2026-03-22T12:00:00"
    }
  ],
  "total": 1
}
```

### GET /api/agent/journal/stats

Ottieni le statistiche dell'Action Journal.

#### Parametri

Nessuno

#### Risposta

```json
{
  "total_entries": 150,
  "by_tool": {"add_tags": 50, "delete_tags": 30, "scan": 70},
  "by_status": {"completed": 140, "failed": 10}
}
```

---

## Approval Gate

### GET /api/agent/approval

Ottieni l'elenco delle richieste di approvazione in sospeso.

#### Parametri

Nessuno

#### Risposta

```json
{
  "pending": [
    {
      "request_id": "req_abc123",
      "tool_name": "purge_deleted",
      "params": {},
      "requested_at": "2026-03-22T12:00:00"
    }
  ],
  "count": 1
}
```

### POST /api/agent/approval/\<request_id\>

Rispondi a una richiesta di approvazione.

#### Rate Limit

WRITE

#### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `request_id` | string | ID della richiesta (parametro di percorso) |

#### Richiesta

```json
{
  "decision": "allow"
}
```

| Parametro | Tipo | Richiesto | Descrizione |
|-----------|------|----------|-------------|
| `decision` | string | Sì | `"allow"` (consenti), `"deny"` (nega), `"always_allow"` (consenti sempre) |

#### Risposta

```json
{
  "ok": true,
  "request_id": "req_abc123",
  "decision": "allow"
}
```

#### Errori

- `400`: `decision` non è uno di `allow`/`deny`/`always_allow`
- `404`: Richiesta non trovata o già responduta

### GET /api/agent/approval/history

Ottieni la cronologia dell'approvazione.

#### Parametri

| Parametro | Tipo | Richiesto | Descrizione |
|-----------|------|----------|-------------|
| `limit` | int | No | Max risultati (predefinito: 50, max: 200) |

#### Risposta

```json
{
  "history": [
    {
      "request_id": "req_abc123",
      "tool_name": "purge_deleted",
      "decision": "allow",
      "decided_at": "2026-03-22T12:01:00"
    }
  ]
}
```

---

## Scope Fence

### GET /api/agent/scope

Ottieni lo stato di Scope Fence per tutte le sessioni.

#### Parametri

Nessuno

#### Risposta

```json
{
  "sessions": {
    "abc123": {
      "preset": "tagger",
      "denied": ["purge_deleted", "hard_delete"],
      "name": "Tagger Bot",
      "expires_at": "2026-03-22T14:00:00"
    }
  },
  "count": 1
}
```

### GET /api/agent/scope/\<session_id\>

Ottieni lo scope per una sessione specifica.

#### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `session_id` | string | ID della sessione (parametro di percorso) |

#### Risposta

```json
{
  "preset": "tagger",
  "denied": ["purge_deleted", "hard_delete"],
  "name": "Tagger Bot",
  "expires_at": "2026-03-22T14:00:00"
}
```

#### Errori

- `404`: Scope della sessione non trovato

### POST /api/agent/scope/\<session_id\>

Imposta lo scope della sessione.

#### Rate Limit

WRITE

#### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `session_id` | string | ID della sessione (parametro di percorso) |

#### Richiesta

```json
{
  "preset": "tagger",
  "denied": ["purge_deleted"],
  "name": "Tagger Bot",
  "duration_hours": 2.0
}
```

| Parametro | Tipo | Richiesto | Descrizione |
|-----------|------|----------|-------------|
| `preset` | string | No | Nome del preset: `"read_only"`, `"tagger"`, `"organizer"`, `"full_access"` |
| `denied` | string[] | No | Elenco dei nomi degli strumenti negati |
| `name` | string | No | Nome di visualizzazione dello scope |
| `duration_hours` | number | No | Scadenza dello scope in ore |

#### Risposta

```json
{
  "ok": true,
  "scope": {
    "preset": "tagger",
    "denied": ["purge_deleted"],
    "name": "Tagger Bot",
    "expires_at": "2026-03-22T14:00:00"
  }
}
```

#### Errori

- `400`: `denied` non è un elenco

### DELETE /api/agent/scope/\<session_id\>

Elimina lo scope di una sessione.

#### Rate Limit

WRITE

#### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `session_id` | string | ID della sessione (parametro di percorso) |

#### Risposta

```json
{
  "ok": true
}
```

---

## Regole Auto-Approve

### GET /api/agent/auto-approve

Ottieni l'elenco delle regole di auto-approvazione.

#### Parametri

Nessuno

#### Risposta

```json
{
  "rules": [
    {
      "index": 0,
      "tool": "add_tags",
      "conditions": {"max_count": 10}
    }
  ]
}
```

### POST /api/agent/auto-approve

Aggiungi una regola di auto-approvazione.

#### Rate Limit

WRITE

#### Richiesta

```json
{
  "tool": "add_tags",
  "conditions": {"max_count": 10}
}
```

| Parametro | Tipo | Richiesto | Descrizione |
|-----------|------|----------|-------------|
| `tool` | string | Sì | Nome dello strumento di destinazione |
| `conditions` | object | No | Condizioni per l'auto-approvazione. Ometti per approvazione incondizionata |

#### Risposta

```json
{
  "ok": true,
  "rule": {
    "index": 1,
    "tool": "add_tags",
    "conditions": {"max_count": 10}
  }
}
```

#### Errori

- `400`: `tool` non specificato
- `400`: `conditions` non è un dict

### DELETE /api/agent/auto-approve/\<index\>

Elimina una regola di auto-approvazione.

#### Rate Limit

WRITE

#### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `index` | int | Indice della regola (parametro di percorso) |

#### Risposta

```json
{
  "ok": true
}
```

#### Errori

- `404`: Regola non trovata

---

## Tool Classification

### GET /api/agent/tool-levels

Ottieni informazioni sulla classificazione degli strumenti. Quando viene specificato il parametro `tool`, restituisce il livello per quello strumento specifico. Altrimenti restituisce un riepilogo di tutti gli strumenti e degli override.

#### Parametri

| Parametro | Tipo | Richiesto | Descrizione |
|-----------|------|----------|-------------|
| `tool` | string | No | Nome dello strumento. Se specificato, restituisce solo il livello di quello strumento |

#### Risposta (strumento specifico)

```json
{
  "tool": "purge_deleted",
  "level": "destructive"
}
```

#### Risposta (tutti gli strumenti)

```json
{
  "summary": {
    "safe": ["list_files", "search_files"],
    "write": ["add_tags", "remove_tags"],
    "destructive": ["purge_deleted", "hard_delete"]
  },
  "overrides": {
    "custom_tool": "safe"
  }
}
```

---

## Undo

### POST /api/agent/undo/\<journal_id\>

Annulla un'azione registrata nel journal.

#### Rate Limit

WRITE

#### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `journal_id` | int | ID della voce del journal (parametro di percorso) |

#### Risposta

```json
{
  "ok": true,
  "journal_id": 1,
  "undone_action": "add_tags"
}
```

#### Errori

- `400`: Undo non riuscito (azione non annullabile, già annullata, ecc.)

### GET /api/agent/undoable

Ottieni l'elenco delle azioni annullabili.

#### Parametri

| Parametro | Tipo | Richiesto | Descrizione |
|-----------|------|----------|-------------|
| `session_id` | string | No | Filtra per ID della sessione |
| `limit` | int | No | Max risultati (predefinito: 50, max: 200) |

#### Risposta

```json
{
  "items": [
    {
      "id": 1,
      "tool_name": "add_tags",
      "session_id": "abc123",
      "params": {"file_id": 42, "tags": ["landscape"]},
      "created_at": "2026-03-22T12:00:00"
    }
  ],
  "count": 1
}
```

---

## Anomaly Detection

### GET /api/agent/anomaly

Ottieni lo stato di Anomaly Detection.

#### Parametri

Nessuno

#### Risposta

```json
{
  "enabled": true,
  "window_minutes": 10,
  "thresholds": {
    "max_actions_per_window": 100,
    "max_errors_per_window": 20
  },
  "current": {
    "actions": 15,
    "errors": 0
  }
}
```

### GET /api/agent/anomaly/alerts

Ottieni gli alert di Anomaly Detection.

#### Parametri

| Parametro | Tipo | Richiesto | Descrizione |
|-----------|------|----------|-------------|
| `limit` | int | No | Max risultati (predefinito: 50, max: 200) |

#### Risposta

```json
{
  "alerts": [
    {
      "id": 1,
      "type": "high_error_rate",
      "message": "Error rate exceeded threshold",
      "severity": "warning",
      "created_at": "2026-03-22T12:00:00"
    }
  ]
}
```

### POST /api/agent/anomaly/reset

Reimposta la cronologia e gli alert di Anomaly Detection.

#### Rate Limit

WRITE

#### Richiesta

Nessuna (corpo vuoto)

#### Risposta

```json
{
  "ok": true
}
```

---

## Audit Bureau

### GET /api/agent/audit

Ottieni lo stato di Audit Bureau.

#### Parametri

Nessuno

#### Risposta

```json
{
  "data": {
    "total_entries": 500,
    "unacknowledged": 3,
    "last_report_at": "2026-03-22T00:00:00"
  }
}
```

### GET /api/agent/audit/log

Ricerca nel Audit Log.

#### Parametri

| Parametro | Tipo | Richiesto | Descrizione |
|-----------|------|----------|-------------|
| `event_type` | string | No | Filtra per tipo di evento |
| `severity` | string | No | Filtra per gravità |
| `source` | string | No | Filtra per fonte |
| `unacknowledged` | string | No | Impostare su `"1"` o `"true"` per restituire solo le voci non riconosciute |
| `limit` | int | No | Max risultati (predefinito: 50, max: 200) |
| `offset` | int | No | Offset (predefinito: 0) |

#### Risposta

```json
{
  "data": {
    "entries": [
      {
        "id": 1,
        "event_type": "kill_switch_activated",
        "severity": "critical",
        "source": "api",
        "message": "Kill switch activated: Manual kill via API",
        "acknowledged": false,
        "created_at": "2026-03-22T12:00:00"
      }
    ],
    "total": 1
  }
}
```

### POST /api/agent/audit/acknowledge/\<audit_id\>

Contrassegna una voce del audit log come riconosciuta dall'utente.

#### Rate Limit

WRITE

#### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `audit_id` | int | ID della voce del audit log (parametro di percorso) |

#### Risposta

```json
{
  "ok": true,
  "audit_id": 1
}
```

#### Errori

- `404`: Voce non trovata o già riconosciuta

### POST /api/agent/audit/report

Genera manualmente un report periodico di Audit Bureau.

#### Rate Limit

WRITE

#### Richiesta

```json
{
  "hours": 24
}
```

| Parametro | Tipo | Richiesto | Descrizione |
|-----------|------|----------|-------------|
| `hours` | int | No | Periodo del report in ore. Predefinito: 24, max: 720 |

#### Risposta

```json
{
  "data": {
    "period_hours": 24,
    "total_events": 150,
    "by_severity": {"critical": 2, "warning": 10, "info": 138},
    "by_type": {"kill_switch_activated": 2, "approval_denied": 5},
    "generated_at": "2026-03-22T12:00:00"
  }
}
```
