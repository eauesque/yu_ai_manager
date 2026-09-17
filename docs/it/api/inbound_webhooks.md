# API Webhook in entrata

Un endpoint di ricezione per l'invio di eventi da servizi esterni a yu_ai_manager event_bus.

## Endpoint di ricezione (Nessuna auth richiesta — basata su token)

`POST /api/webhooks/receive/{token}`

### Corpo della richiesta

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| event | string | event_type da attivare (predefinito: `webhook.received`) |
| data | object | Dati dell'evento |

### Risposta

```json
{"ok": true, "event": "scan.start"}
```

### Errori

| Codice | Descrizione |
|--------|-------------|
| 403 | Token non valido / mancata corrispondenza HMAC / evento non in allowed_events |

## API di gestione (Sessione PIN richiesta)

### Crea

`POST /api/webhooks/inbound`

```json
{"label": "n8n trigger", "allowed_events": ["scan.start"]}
```

Risposta:

```json
{
  "id": "iwh_a1b2c3...",
  "token": "64char_hex...",
  "label": "n8n trigger",
  "allowed_events": ["scan.start"],
  "active": true,
  "created_at": 1712188800
}
```

### Elenco

`GET /api/webhooks/inbound`

### Aggiorna

`PUT /api/webhooks/inbound/{id}`

```json
{"label": "updated", "allowed_events": ["scan.start", "tag.add"], "active": true}
```

### Elimina

`DELETE /api/webhooks/inbound/{id}`

## Autenticazione

- Accettato se il token nell'URL corrisponde
- Se è presente l'intestazione `X-Webhook-Signature`, viene eseguita una verifica HMAC-SHA256 aggiuntiva (opzionale)

## Sicurezza

- Token è 64 caratteri esadecimali (256 bit)
- `allowed_events` limita quali eventi possono essere attivati
- Array `allowed_events` vuoto = tutti gli eventi consentiti
