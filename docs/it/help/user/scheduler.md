# Task Scheduler

## Panoramica

Lo scheduler esegue automaticamente task periodici come manutenzione database e polling servizi esterni. Usa APScheduler per gestire job con trigger cron / interval.

Dalla pagina scheduler WebUI (`/scheduler`), visualizza elenco job, aggiungi, rimuovi, sospendi, esegui subito.

## Setup

Lo scheduler è abilitato per impostazione predefinita. Controlla con `scheduler.enabled` in `config.json`:

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

Job scritti in `config.json` auto-registrati al boot server. Job aggiunti da WebUI validi solo durante sessione server (persi al riavvio).

## Elenco job built-in

### Manutenzione database

| Job ID | Descrizione | Frequenza consigliata |
|-----------|------|---------|
| `db_vacuum` | Esegui SQLite VACUUM, recupera spazio non usato | Settimanale |
| `db_integrity_check` | Valida integrità DB con `PRAGMA integrity_check` | Giornaliero |
| `db_backup` | Crea backup database (via extension builtin-backup) | Giornaliero |

### Gestione cache e indice

| Job ID | Descrizione | Frequenza consigliata |
|-----------|------|---------|
| `thumbnail_cleanup` | Cancella file cache miniatura scaduti | Giornaliero |
| `prune_unused_tags` | Cancella record tag orfani non collegati a file | Settimanale-mensile |
| `refresh_monthly_stats` | Aggiorna cache precalcolata statistiche mensili | Giornaliero |
| `rebuild_groups_index` | Ricostruisci cache indice gruppi cartella/archivio | Settimanale |

### Integrazione servizi esterni

| Job ID | Descrizione | Frequenza consigliata |
|-----------|------|---------|
| `github_issue_poll` | Poll GitHub API, importa issue nuove a queue locale | 5min-1ora |
| `bsky_notification_poll` | Poll Bluesky API, ottieni notifiche nuove | 5min-1ora |

## Configurazione trigger

### Trigger cron

Esegui a orario/giorno/data specifici. Simile a cron Unix.

| Parametro | Valori esempio | Descrizione |
|-----------|--------|------|
| `hour` | `3`, `*/6`, `1,13` | Ora (0-23). `*` per ogni ora |
| `minute` | `0`, `30`, `0,30` | Minuto (0-59). `*` per ogni minuto |
| `day` | `1`, `15`, `1,15` | Giorno (1-31). `*` per ogni giorno |
| `day_of_week` | `sun`, `mon-fri`, `0-4` | Giorno settimana. `*` per ogni giorno |

**Esempio**: Esegui 1 e 15 del mese alle 02:30

```json
{ "trigger": "cron", "day": "1,15", "hour": 2, "minute": 30 }
```

### Trigger interval

Ripeti a intervalli fissi.

| Parametro | Valori esempio | Descrizione |
|-----------|--------|------|
| `hours` | `2` | Intervallo ore |
| `minutes` | `30` | Intervallo minuti |
