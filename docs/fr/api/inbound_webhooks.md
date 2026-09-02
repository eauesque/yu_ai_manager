# API Webhook entrant

Un point d'accès de réception pour envoyer des événements de services externes vers l'event_bus du yu_ai_manager.

## Point d'accès de réception (Aucune authentification requise — basée sur le token)

`POST /api/webhooks/receive/{token}`

### Corps de la requête

| Champ | Type | Description |
|-------|------|-------------|
| event | string | event_type à déclencher (par défaut : `webhook.received`) |
| data | object | Données d'événement |

### Réponse

```json
{"ok": true, "event": "scan.start"}
```

### Erreurs

| Code | Description |
|------|-------------|
| 403 | Token invalide / Non-correspondance HMAC / événement non dans allowed_events |

## API de gestion (Session PIN requise)

### Créer

`POST /api/webhooks/inbound`

```json
{"label": "n8n trigger", "allowed_events": ["scan.start"]}
```

Réponse :

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

### Lister

`GET /api/webhooks/inbound`

### Mettre à jour

`PUT /api/webhooks/inbound/{id}`

```json
{"label": "updated", "allowed_events": ["scan.start", "tag.add"], "active": true}
```

### Supprimer

`DELETE /api/webhooks/inbound/{id}`

## Authentification

- Accepté si le token dans l'URL correspond
- Si l'en-tête `X-Webhook-Signature` est présent, une vérification HMAC-SHA256 supplémentaire est effectuée (optionnel)

## Sécurité

- Le token est un hex de 64 caractères (256 bits)
- `allowed_events` restreint les événements qui peuvent être déclenchés
- Tableau `allowed_events` vide = tous les événements autorisés
