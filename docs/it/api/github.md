# API Integrazione GitHub

API per la gestione degli account GitHub, problemi, pull request, notifiche e rilasci.

Fornito dall'estensione `builtin-github`. Tutti gli endpoint richiedono autenticazione (sessione PIN o chiave API).

## Gestione Account

### GET /api/github/accounts

Elenca gli account GitHub registrati. I token vengono mascherati nella risposta.

### Risposta

```json
{
  "data": [
    {
      "label": "my-account",
      "token": "ghp_****...xxxx",
      "repos": ["owner/repo1", "owner/repo2"],
      "enabled": true
    }
  ]
}
```

### POST /api/github/accounts

Registra un nuovo account GitHub.

### Richiesta

```json
{
  "label": "my-account",
  "token": "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "repos": ["owner/repo1", "owner/repo2"]
}
```

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|----------|-------------|
| `label` | string | Yes | Etichetta identificatrice account univoca |
| `token` | string | Yes | Token di Accesso Personale GitHub |
| `repos` | string[] | Yes | Repository da monitorare (formato `owner/repo`) |

### Risposta

```json
{
  "data": { "label": "my-account", "status": "created" }
}
```

### PUT /api/github/accounts/<label>

Aggiorna le impostazioni di un account esistente.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `label` | string | Etichetta account (parametro di percorso) |

### Richiesta

```json
{
  "token": "ghp_new_token_value",
  "repos": ["owner/repo1", "owner/repo3"],
  "enabled": false
}
```

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|----------|-------------|
| `token` | string | No | Nuovo valore token |
| `repos` | string[] | No | Elenco repository aggiornato |
| `enabled` | boolean | No | Abilita o disabilita l'account |

### DELETE /api/github/accounts/<label>

Rimuovi un account.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `label` | string | Etichetta account (parametro di percorso) |

---

## Problemi

### GET /api/github/issues/<label>

Recupera i problemi dai repository dell'account.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `label` | string | Etichetta account (parametro di percorso) |
| `state` | string | Filtro dello stato del problema (`open`, `closed`, `all`) |
| `labels` | string | Filtro delle etichette (separate da virgola) |
| `since` | string | Problemi aggiornati dopo questa data (ISO 8601) |
| `repo` | string | Filtra a un repository specifico (`owner/repo`) |

### Esempio curl

```bash
curl -H "Authorization: Bearer sk_xxxxx" \
  "http://localhost:5000/api/github/issues/my-account?state=open&repo=owner/repo1"
```

### POST /api/github/issues/<label>

Crea un nuovo problema.

### Richiesta

```json
{
  "repo": "owner/repo1",
  "title": "Bug: crash on login screen",
  "body": "Steps to reproduce:\n1. ...\n2. ...",
  "labels": ["bug", "priority:high"]
}
```

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|----------|-------------|
| `repo` | string | Yes | Repository target (`owner/repo`) |
| `title` | string | Yes | Titolo del problema |
| `body` | string | No | Corpo del problema (Markdown) |
| `labels` | string[] | No | Etichette da applicare |

### GET /api/github/issue/<label>/<repo>/<number>

Recupera i dettagli del problema inclusi i commenti.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `label` | string | Etichetta account |
| `repo` | string | Nome repository (`owner/repo`) |
| `number` | int | Numero del problema |

### POST /api/github/triage/<label>

Esegui il triage del problema (classificazione e prioritizzazione).

### Richiesta

```json
{
  "state": "open",
  "since": "2026-03-01T00:00:00Z"
}
```

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|----------|-------------|
| `state` | string | No | Filtro dello stato per i problemi target |
| `since` | string | No | Esegui il triage solo dei problemi aggiornati dopo questa data (ISO 8601) |

---

## Pull Request

### GET /api/github/pulls/<label>

Elenca le pull request.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `label` | string | Etichetta account (parametro di percorso) |
| `state` | string | Stato PR (`open`, `closed`, `all`) |
| `repo` | string | Filtra a un repository specifico (`owner/repo`) |

### GET /api/github/pull/<label>/<repo>/<number>

Recupera i dettagli della PR inclusi i file modificati.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `label` | string | Etichetta account |
| `repo` | string | Nome repository (`owner/repo`) |
| `number` | int | Numero della PR |

---

## Notifiche

### GET /api/github/notifications/<label>

Elenca le notifiche.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `label` | string | Etichetta account (parametro di percorso) |
| `all` | string | Impostare su `true` per includere le notifiche lette (predefinito: solo non lette) |

### PATCH /api/github/notifications/<label>/<thread_id>

Contrassegna un thread di notifica specifico come letto.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `label` | string | Etichetta account |
| `thread_id` | string | ID del thread di notifica |

### POST /api/github/notifications/<label>/mark-all-read

Contrassegna tutte le notifiche come lette.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `label` | string | Etichetta account (parametro di percorso) |

---

## Discussioni

### GET /api/github/discussions/<label>

Recupera GitHub Discussions (tramite API GraphQL).

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `label` | string | Etichetta account (parametro di percorso) |
| `repo` | string | Filtra a un repository specifico (`owner/repo`) |

---

## Rilasci

### GET /api/github/releases/<label>

Elenca i rilasci.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `label` | string | Etichetta account (parametro di percorso) |
| `repo` | string | Filtra a un repository specifico (`owner/repo`) |

---

## Statistiche Repository

### GET /api/github/repo-stats/<label>/<repo>

Recupera le statistiche per un repository singolo.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `label` | string | Etichetta account |
| `repo` | string | Nome repository (`owner/repo`) |

### GET /api/github/repo-stats-all/<label>

Recupera le statistiche per tutti i repository registrati in una volta.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `label` | string | Etichetta account (parametro di percorso) |

---

## Limite di Velocità

### GET /api/github/rate-limit/<label>

Verifica lo stato del limite di velocità API GitHub.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `label` | string | Etichetta account (parametro di percorso) |

### Esempio di Risposta

```json
{
  "data": {
    "rate": {
      "limit": 5000,
      "remaining": 4832,
      "reset": 1710500000
    }
  }
}
```

---

## Prompt di Triage

### GET /api/github/triage-prompts

Ottieni i prompt di triage modificabili per problema/PR/discussione, insieme ai loro valori predefiniti.

### Risposta

```json
{
  "data": {
    "prompts": {
      "issue": "Review the following GitHub issue...",
      "pr": "Do not accept pull requests. Close automatically.",
      "discussion": "Discussions are closed. No action required."
    },
    "defaults": {
      "issue": "Review the following GitHub issue...",
      "pr": "Do not accept pull requests. Close automatically.",
      "discussion": "Discussions are closed. No action required."
    }
  }
}
```

### PUT /api/github/triage-prompts

Aggiorna i prompt di triage. Solo i campi forniti vengono aggiornati.

### Richiesta

```json
{
  "issue": "Custom issue triage prompt...",
  "pr": "Custom PR prompt...",
  "discussion": "Custom discussion prompt..."
}
```

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|----------|-------------|
| `issue` | string | No | Prompt di triage per i problemi |
| `pr` | string | No | Prompt di triage per le pull request |
| `discussion` | string | No | Prompt di triage per le discussioni |

---

## Coda Problemi

### GET /api/github/queue

Ottieni gli elementi della coda dei problemi con filtro di stato opzionale.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `status` | string | Filtra: `pending`, `notified`, `dismissed`, o vuoto per tutti |
| `limit` | int | Max risultati (predefinito 50, max 200) |

### Risposta

```json
{
  "data": {
    "items": [
      {
        "id": 1,
        "repo": "owner/repo",
        "issue_number": 42,
        "title": "Bug report title",
        "body": "Issue body...",
        "created_at": "2026-03-15T10:00:00Z",
        "fetched_at": "2026-03-15T12:00:00Z",
        "status": "pending",
        "triage_result": "pending"
      }
    ],
    "stats": { "pending": 3, "notified": 1, "dismissed": 5, "total": 9 }
  }
}
```

### GET /api/github/queue/pending

Ottieni i problemi in sospeso (non letti) per la notifica MCP.

### Risposta

```json
{
  "data": {
    "items": [...],
    "count": 3
  }
}
```

### POST /api/github/queue/<queue_id>/triage

Imposta il risultato del triage per un elemento della coda.

### Richiesta

```json
{ "result": "valid" }
```

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|----------|-------------|
| `result` | string | Yes | `valid` o `invalid` |

### POST /api/github/queue/<queue_id>/dismiss

Scarta un elemento della coda. Facoltativamente chiudi automaticamente il problema su GitHub.

### Richiesta

```json
{
  "auto_close": true,
  "account_label": "my-account"
}
```

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|----------|-------------|
| `auto_close` | boolean | No | Chiudi il problema su GitHub con un commento del modello |
| `account_label` | string | No | Obbligatorio se `auto_close` è true |

### PUT /api/github/queue/<queue_id>/status

Aggiorna lo stato dell'elemento della coda.

### Richiesta

```json
{ "status": "notified" }
```

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|----------|-------------|
| `status` | string | Yes | `pending`, `notified`, o `dismissed` |

### GET /api/github/queue/config

Ottieni la configurazione della coda dei problemi.

### Risposta

```json
{
  "data": {
    "poll_interval_minutes": 60,
    "auto_close_invalid": false,
    "notify_on_connect": true
  }
}
```

### PUT /api/github/queue/config

Aggiorna la configurazione della coda dei problemi.

### Richiesta

```json
{
  "poll_interval_minutes": 30,
  "auto_close_invalid": true,
  "notify_on_connect": true
}
```

### POST /api/github/queue/poll

Attiva il polling immediato di tutti gli account per i nuovi problemi.

---

## WebUI

### GET /ext/github

Pagina WebUI di Integrazione GitHub. Accedi direttamente nel browser.

Richiede una sessione PIN autenticata.
