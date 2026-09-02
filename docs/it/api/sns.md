# API Condivisione SNS

API per la condivisione SNS, la pubblicazione su Bluesky e la gestione della coda di notifiche.

Fornito da `routes/sns_share.py`. Tutti gli endpoint richiedono autenticazione (sessione PIN o chiave API).

## Anteprima e Intent X

### GET /api/sns/preview

Espandi un modello di post con i metadati dell'immagine e restituisci un'anteprima. Utile per visualizzare in anteprima cosa verrà pubblicato prima della condivisione.

### Parametri

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | ID file immagine target |
| `template` | string | No | Stringa del modello personalizzato (utilizza il predefinito se omesso) |

### Risposta

```json
{
  "text": "New artwork: sunset landscape #aiart #stablediffusion",
  "graphemes": 52,
  "meta": {
    "title": "sunset landscape",
    "model": "sd_xl_base_1.0",
    "generator": "a1111"
  }
}
```

### Esempio curl

```bash
curl -H "Authorization: Bearer sk_xxxxx" \
  "http://localhost:5000/api/sns/preview?file_id=42"
```

### GET /api/sns/x/intent

Genera un URL di Web Intent X (Twitter) per la condivisione. Apre la finestra di dialogo di composizione X con il testo precompilato.

### Parametri

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | ID file immagine target |

### Risposta

```json
{
  "url": "https://twitter.com/intent/tweet?text=New+artwork%3A+sunset+landscape+%23aiart"
}
```

---

## Pubblicazione Bluesky

### POST /api/sns/bluesky/post

Pubblica testo (e facoltativamente un'immagine) su Bluesky.

### Richiesta

```json
{
  "file_id": 42,
  "text": "Check out my new artwork! #aiart",
  "attach_image": true
}
```

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|----------|-------------|
| `file_id` | int | Yes | ID file immagine target |
| `text` | string | No | Testo del post (utilizza l'espansione del modello se omesso) |
| `attach_image` | boolean | No | Allega l'immagine al post (predefinito: false) |

### Risposta

```json
{
  "ok": true,
  "uri": "at://did:plc:xxxxx/app.bsky.feed.post/yyyyy"
}
```

### Risposta di Errore

```json
{
  "ok": false,
  "error": "Authentication failed: invalid app password"
}
```

### POST /api/sns/bluesky/test

Testa la connessione Bluesky con le credenziali configurate.

### Risposta

```json
{
  "ok": true,
  "handle": "user.bsky.social",
  "display_name": "My Display Name"
}
```

### Risposta di Errore

```json
{
  "ok": false,
  "error": "Invalid identifier or password"
}
```

---

## Configurazione SNS

### GET /api/sns/config

Ottieni la configurazione SNS. Le password vengono mascherate nella risposta.

### Risposta

```json
{
  "bluesky": {
    "handle": "user.bsky.social",
    "app_password": "****...xxxx"
  },
  "post_template": "{title} #aiart #{generator}"
}
```

### POST /api/sns/config

Salva la configurazione SNS.

### Richiesta

```json
{
  "bluesky_handle": "user.bsky.social",
  "bluesky_app_password": "xxxx-xxxx-xxxx-xxxx",
  "post_template": "{title} #aiart #{generator}"
}
```

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|----------|-------------|
| `bluesky_handle` | string | No | Handle Bluesky (es. `user.bsky.social`) |
| `bluesky_app_password` | string | No | Password Applicazione Bluesky |
| `post_template` | string | No | Modello di post predefinito con variabili `{placeholder}` |

### Esempio curl

```bash
curl -X POST -H "Authorization: Bearer sk_xxxxx" \
  -H "Content-Type: application/json" \
  -H "X-Requested-With: XMLHttpRequest" \
  -d '{"bluesky_handle": "user.bsky.social", "bluesky_app_password": "xxxx-xxxx-xxxx-xxxx"}' \
  "http://localhost:5000/api/sns/config"
```

---

## Coda Notifiche Bluesky

### GET /api/sns/bsky/queue

Elenca gli elementi della coda di notifiche con filtri opzionali.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `status` | string | Filtra: `pending`, `notified`, `dismissed`, o vuoto per tutti |
| `type` | string | Filtro del tipo di notifica (es. `mention`, `reply`, `quote`, `like`, `repost`, `follow`) |
| `limit` | int | Max risultati (predefinito 50) |

### Risposta

```json
{
  "data": {
    "items": [
      {
        "id": 1,
        "type": "mention",
        "author_handle": "someone.bsky.social",
        "author_display_name": "Someone",
        "text": "@user.bsky.social great artwork!",
        "uri": "at://did:plc:xxxxx/app.bsky.feed.post/yyyyy",
        "created_at": "2026-03-15T10:00:00Z",
        "fetched_at": "2026-03-15T12:00:00Z",
        "status": "pending",
        "triage_result": null
      }
    ],
    "stats": { "pending": 3, "notified": 1, "dismissed": 5, "total": 9 }
  }
}
```

### GET /api/sns/bsky/queue/pending

Ottieni le notifiche in sospeso (non elaborate) per la notifica MCP.

### Risposta

```json
{
  "data": {
    "items": [...],
    "count": 3,
    "stats": { "pending": 3, "notified": 1, "dismissed": 5, "total": 9 }
  }
}
```

### POST /api/sns/bsky/queue/<queue_id>/triage

Imposta il risultato del triage per un elemento della coda.

### Richiesta

```json
{ "result": "valid" }
```

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|----------|-------------|
| `result` | string | Yes | `valid` o `invalid` |

### PUT /api/sns/bsky/queue/<queue_id>/status

Aggiorna lo stato dell'elemento della coda.

### Richiesta

```json
{ "status": "notified" }
```

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|----------|-------------|
| `status` | string | Yes | `pending`, `notified`, o `dismissed` |

### POST /api/sns/bsky/queue/<queue_id>/respond

Invia una risposta automatica a una notifica.

### Richiesta

```json
{ "text": "Thank you for your kind words!" }
```

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|----------|-------------|
| `text` | string | Yes | Testo della risposta da pubblicare come risposta |

### POST /api/sns/bsky/queue/poll

Attiva il polling immediato per le nuove notifiche Bluesky.

### Esempio curl

```bash
curl -X POST -H "Authorization: Bearer sk_xxxxx" \
  -H "X-Requested-With: XMLHttpRequest" \
  "http://localhost:5000/api/sns/bsky/queue/poll"
```

---

## Configurazione Monitor Bluesky

### GET /api/sns/bsky/monitor/config

Ottieni le impostazioni del monitor di notifiche Bluesky.

### Risposta

```json
{
  "data": {
    "poll_interval_minutes": 15,
    "auto_dismiss_follow": false,
    "auto_dismiss_like": true,
    "auto_dismiss_repost": true,
    "auto_respond_enabled": false,
    "notify_on_connect": true
  }
}
```

### PUT /api/sns/bsky/monitor/config

Aggiorna le impostazioni del monitor di notifiche Bluesky. Solo i campi forniti vengono aggiornati.

### Richiesta

```json
{
  "poll_interval_minutes": 30,
  "auto_dismiss_follow": false,
  "auto_dismiss_like": true,
  "auto_dismiss_repost": true,
  "auto_respond_enabled": false,
  "notify_on_connect": true
}
```

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|----------|-------------|
| `poll_interval_minutes` | int | No | Intervallo di polling in minuti |
| `auto_dismiss_follow` | boolean | No | Automaticamente ignora le notifiche di follow |
| `auto_dismiss_like` | boolean | No | Automaticamente ignora le notifiche di like |
| `auto_dismiss_repost` | boolean | No | Automaticamente ignora le notifiche di repost |
| `auto_respond_enabled` | boolean | No | Abilita le risposte automatiche |
| `notify_on_connect` | boolean | No | Invia notifica al client MCP al collegamento |

---

## Prompt di Triage e Modelli di Risposta Automatica

### GET /api/sns/bsky/monitor/triage-prompts

Ottieni i prompt di triage modificabili, i modelli di risposta automatica e i loro valori predefiniti.

### Risposta

```json
{
  "data": {
    "triage_prompts": {
      "mention": "Evaluate this mention for relevance...",
      "reply": "Evaluate this reply...",
      "quote": "Evaluate this quote post..."
    },
    "auto_responses": {
      "mention": "Thanks for the mention!",
      "reply": "Thank you for your reply!",
      "quote": "Thanks for sharing!"
    },
    "defaults": {
      "triage_prompts": {
        "mention": "Evaluate this mention for relevance...",
        "reply": "Evaluate this reply...",
        "quote": "Evaluate this quote post..."
      },
      "auto_responses": {
        "mention": "Thanks for the mention!",
        "reply": "Thank you for your reply!",
        "quote": "Thanks for sharing!"
      }
    }
  }
}
```

### PUT /api/sns/bsky/monitor/triage-prompts

Aggiorna i prompt di triage e/o i modelli di risposta automatica. Solo i campi forniti vengono aggiornati.

### Richiesta

```json
{
  "triage_prompts": {
    "mention": "Custom mention triage prompt...",
    "reply": "Custom reply triage prompt...",
    "quote": "Custom quote triage prompt..."
  },
  "auto_responses": {
    "mention": "Custom mention auto-response...",
    "reply": "Custom reply auto-response...",
    "quote": "Custom quote auto-response..."
  }
}
```

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|----------|-------------|
| `triage_prompts` | object | No | Prompt di triage chiave per tipo di notifica (`mention`, `reply`, `quote`) |
| `auto_responses` | object | No | Modelli di risposta automatica chiave per tipo di notifica |
