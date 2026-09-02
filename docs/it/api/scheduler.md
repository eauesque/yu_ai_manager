# API Scheduler

API di gestione per lo scheduler di attività. Permette di verificare lo stato, aggiungere/rimuovere lavori, mettere in pausa/riprendere, attivare l'esecuzione immediata e recuperare la cronologia di esecuzione.

## Configurazione

Abilita lo scheduler e configura i programmi dei lavori integrati in `config.json`:

```json
{
  "scheduler": {
    "enabled": true,
    "jobs": {
      "db_vacuum": { "enabled": true, "trigger": "cron", "day_of_week": "sun", "hour": 3, "minute": 0 },
      "db_integrity_check": { "enabled": true, "trigger": "cron", "hour": 4, "minute": 0 },
      "thumbnail_cleanup": { "enabled": true, "trigger": "cron", "hour": 5, "minute": 0 }
    }
  }
}
```

### Lavori Integrati

| ID Lavoro | Descrizione | Programma Predefinito |
|--------|-------------|-----------------|
| `db_vacuum` | VACUUM del database (recupera spazio) | Ogni domenica alle 03:00 |
| `db_integrity_check` | Controllo di integrità del database | Ogni giorno alle 04:00 |
| `thumbnail_cleanup` | Pulizia della cache delle miniature | Ogni giorno alle 05:00 |
| `github_issue_poll` | Polling dei problemi GitHub | Non impostato (aggiungere tramite WebUI) |
| `bsky_notification_poll` | Polling delle notifiche Bluesky | Non impostato (aggiungere tramite WebUI) |
| `prune_unused_tags` | Eliminazione dei tag non utilizzati | Non impostato (aggiungere tramite WebUI) |
| `refresh_monthly_stats` | Aggiorna la cache delle statistiche mensili | Non impostato (aggiungere tramite WebUI) |
| `rebuild_groups_index` | Ricostruisci l'indice dei gruppi | Non impostato (aggiungere tramite WebUI) |
| `db_backup` | Backup del database | Non impostato (aggiungere tramite WebUI) |

## GET /api/scheduler/status

Restituisce lo stato dello scheduler e le informazioni su tutti i lavori.

### Risposta

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `ok` | boolean | Flag di successo |
| `data.running` | boolean | Se lo scheduler è in esecuzione |
| `data.jobs` | array | Elenco dei lavori (inclusi i tempi di esecuzione successivi) |

### Esempio

```bash
curl "http://localhost:5100/api/scheduler/status"
```

```json
{
  "ok": true,
  "data": {
    "running": true,
    "jobs": [
      {
        "job_id": "db_vacuum",
        "trigger": "cron",
        "next_run": "2026-03-22T03:00:00",
        "paused": false
      },
      {
        "job_id": "db_integrity_check",
        "trigger": "cron",
        "next_run": "2026-03-16T04:00:00",
        "paused": false
      }
    ]
  }
}
```

## GET /api/scheduler/jobs

Restituisce l'elenco dei lavori con i tempi di `next_run`.

### Risposta

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `ok` | boolean | Flag di successo |
| `data.jobs` | array | Array di oggetti lavoro |
| `data.jobs[].job_id` | string | ID del lavoro |
| `data.jobs[].func_name` | string | Nome della funzione da eseguire |
| `data.jobs[].trigger` | string | Tipo di trigger (`cron`, `interval`, `date`) |
| `data.jobs[].next_run` | string | Ora di esecuzione programmata successiva (ISO 8601) |
| `data.jobs[].paused` | boolean | Se il lavoro è in pausa |

### Esempio

```bash
curl "http://localhost:5100/api/scheduler/jobs"
```

```json
{
  "ok": true,
  "data": {
    "jobs": [
      {
        "job_id": "db_vacuum",
        "func_name": "db_vacuum",
        "trigger": "cron",
        "next_run": "2026-03-22T03:00:00",
        "paused": false
      }
    ]
  }
}
```

## POST /api/scheduler/jobs

Aggiungi un lavoro personalizzato.

### Corpo della Richiesta

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|----------|-------------|
| `job_id` | string | Yes | ID lavoro univoco |
| `func_name` | string | Yes | Nome della funzione da eseguire |
| `trigger` | string | Yes | Tipo di trigger (`cron`, `interval`, `date`) |
| `trigger_args` | object | Yes | Argomenti del trigger (`hour`, `minute`, `day_of_week`, ecc.) |

### Esempio

```bash
curl -X POST "http://localhost:5100/api/scheduler/jobs" \
     -H "X-Requested-With: XMLHttpRequest" \
     -H "Content-Type: application/json" \
     -d '{
       "job_id": "custom_cleanup",
       "func_name": "thumbnail_cleanup",
       "trigger": "cron",
       "trigger_args": { "hour": 6, "minute": 30 }
     }'
```

```json
{
  "ok": true,
  "data": {
    "job_id": "custom_cleanup",
    "next_run": "2026-03-16T06:30:00"
  }
}
```

## DELETE /api/scheduler/jobs/\<id\>

Rimuovi un lavoro. Soggetto al limite di velocità del tier **DESTRUCTIVE**.

### Parametri di Percorso

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `id` | string | ID del lavoro |

### Esempio

```bash
curl -X DELETE "http://localhost:5100/api/scheduler/jobs/custom_cleanup" \
     -H "X-Requested-With: XMLHttpRequest"
```

```json
{
  "ok": true,
  "data": { "removed": "custom_cleanup" }
}
```

## POST /api/scheduler/jobs/\<id\>/pause

Metti in pausa un lavoro.

### Esempio

```bash
curl -X POST "http://localhost:5100/api/scheduler/jobs/db_vacuum/pause" \
     -H "X-Requested-With: XMLHttpRequest"
```

```json
{
  "ok": true,
  "data": { "job_id": "db_vacuum", "paused": true }
}
```

## POST /api/scheduler/jobs/\<id\>/resume

Riprendi un lavoro in pausa.

### Esempio

```bash
curl -X POST "http://localhost:5100/api/scheduler/jobs/db_vacuum/resume" \
     -H "X-Requested-With: XMLHttpRequest"
```

```json
{
  "ok": true,
  "data": { "job_id": "db_vacuum", "paused": false }
}
```

## POST /api/scheduler/jobs/\<id\>/trigger

Attiva l'esecuzione immediata di un lavoro. Soggetto al limite di velocità del tier **WRITE**.

### Esempio

```bash
curl -X POST "http://localhost:5100/api/scheduler/jobs/db_vacuum/trigger" \
     -H "X-Requested-With: XMLHttpRequest"
```

```json
{
  "ok": true,
  "data": { "job_id": "db_vacuum", "triggered": true }
}
```

## GET /api/scheduler/history

Restituisce la cronologia di esecuzione in ordine più recente (max 100 voci).

### Risposta

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `ok` | boolean | Flag di successo |
| `data.history` | array | Array di voci di cronologia di esecuzione |
| `data.history[].job_id` | string | ID del lavoro |
| `data.history[].executed_at` | string | Timestamp di esecuzione (ISO 8601) |
| `data.history[].status` | string | Risultato (`success`, `error`) |
| `data.history[].duration_ms` | number | Durata dell'esecuzione (millisecondi) |
| `data.history[].error` | string\|null | Messaggio di errore (solo in caso di fallimento) |

### Esempio

```bash
curl "http://localhost:5100/api/scheduler/history"
```

```json
{
  "ok": true,
  "data": {
    "history": [
      {
        "job_id": "db_integrity_check",
        "executed_at": "2026-03-15T04:00:02",
        "status": "success",
        "duration_ms": 1234,
        "error": null
      },
      {
        "job_id": "thumbnail_cleanup",
        "executed_at": "2026-03-15T05:00:01",
        "status": "success",
        "duration_ms": 567,
        "error": null
      }
    ]
  }
}
```

## Eventi SSE

Gli eventi correlati allo scheduler vengono forniti tramite il motore SSE condiviso.

| Evento | Dati | Descrizione |
|-------|------|-------------|
| `scheduler.job_executed` | `{ job_id, result }` | Esecuzione del lavoro completata |
| `scheduler.job_error` | `{ job_id, error }` | Errore di esecuzione del lavoro |

```javascript
window.sseSubscribe('scheduler.job_executed', (data) => {
  console.log(`Job ${data.job_id} completed: ${data.result}`);
});
```

## Strumenti MCP

| Strumento | Descrizione |
|------|-------------|
| `get_scheduler_status` | Ottieni lo stato di esecuzione dello scheduler |
| `list_scheduled_jobs` | Elenca i lavori registrati |
| `trigger_scheduled_job` | Attiva l'esecuzione immediata del lavoro |
| `pause_scheduled_job` | Metti in pausa un lavoro |
| `resume_scheduled_job` | Riprendi un lavoro |
| `get_scheduler_history` | Ottieni la cronologia di esecuzione |

## Limite di Velocità

| Endpoint | Metodo | Tier |
|----------|--------|------|
| `/api/scheduler/status` | GET | READ (illimitato) |
| `/api/scheduler/jobs` | GET | READ (illimitato) |
| `/api/scheduler/jobs` | POST | WRITE (~120 req/min) |
| `/api/scheduler/jobs/<id>` | DELETE | DESTRUCTIVE (~12 req/min) |
| `/api/scheduler/jobs/<id>/pause` | POST | WRITE (~120 req/min) |
| `/api/scheduler/jobs/<id>/resume` | POST | WRITE (~120 req/min) |
| `/api/scheduler/jobs/<id>/trigger` | POST | WRITE (~120 req/min) |
| `/api/scheduler/history` | GET | READ (illimitato) |
