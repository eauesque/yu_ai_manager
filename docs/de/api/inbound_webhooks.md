# Eingehende Webhook API

Ein Empfangsendpunkt zum Senden von Ereignissen von externen Diensten zum yu_ai_manager event_bus.

## Empfangsendpunkt (Keine Authentifizierung erforderlich — Token-basiert)

`POST /api/webhooks/receive/{token}`

### Anfragekörper

| Feld | Typ | Beschreibung |
|-------|------|-------------|
| event | string | event_type zum Auslösen (Standard: `webhook.received`) |
| data | object | Ereignisdaten |

### Antwort

```json
{"ok": true, "event": "scan.start"}
```

### Fehler

| Code | Beschreibung |
|------|-------------|
| 403 | Ungültiger Token / HMAC-Nichtübereinstimmung / Ereignis nicht in allowed_events |

## Management API (PIN-Sitzung erforderlich)

### Erstellen

`POST /api/webhooks/inbound`

```json
{"label": "n8n trigger", "allowed_events": ["scan.start"]}
```

Antwort:

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

### Auflisten

`GET /api/webhooks/inbound`

### Aktualisieren

`PUT /api/webhooks/inbound/{id}`

```json
{"label": "updated", "allowed_events": ["scan.start", "tag.add"], "active": true}
```

### Löschen

`DELETE /api/webhooks/inbound/{id}`

## Authentifizierung

- Akzeptiert wenn der Token in der URL übereinstimmt
- Wenn der Header `X-Webhook-Signature` vorhanden ist, wird zusätzliche HMAC-SHA256-Überprüfung durchgeführt (optional)

## Sicherheit

- Token ist 64-Zeichen-Hex (256 Bit)
- `allowed_events` beschränkt, welche Ereignisse ausgelöst werden können
- Leeres `allowed_events`-Array = alle Ereignisse erlaubt
