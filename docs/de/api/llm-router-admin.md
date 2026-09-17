# API: /api/llm_router (Admin)

Admin-Endpunkte für LLM Router-Verwaltungsvorgänge. Geschützt durch die standardmäßige WebUI-Sitzungsauthentifizierung (PIN/Sitzung) und völlig separat von der OpenAI-kompatiblen `/v1/*`-Oberfläche.

> **Hinweis**: Dies sind Admin-Endpunkte und unterscheiden sich von Inferenz-Endpunkten wie `/v1/chat/completions`.

---

## Allgemeines Antwortformat

Alle Endpunkte verwenden den `api_result`-Wrapper. Bei Erfolg befindet sich der Körper unter dem Schlüssel `data`.

```json
{
  "status": "ok",
  "data": { ... }
}
```

Bei Fehler:

```json
{
  "status": "error",
  "error": "Fehlerbeschreibung"
}
```

---

## GET /api/llm_router/status

Ein Snapshot für das Rendering des gesamten Dashboards in einer einzigen Anfrage. Gibt alle Backend-Informationen und die Alias-Zuordnung zurück.

### Anfrage

```
GET /api/llm_router/status
```

Keine Parameter.

### Antwort `200 OK`

```json
{
  "status": "ok",
  "data": {
    "router": {
      "version": "1.0.0",
      "alias_count": 2
    },
    "backends": [
      {
        "alias": "ollama-mac",
        "base_url": "http://192.168.1.10:11434",
        "source": "static",
        "status": "ready",
        "slo_state": null,
        "disabled": false,
        "model_count": 3,
        "models": [
          {
            "name": "qwen2.5:7b",
            "context_window": 32768,
            "size_b": 7.6
          },
          {
            "name": "llama3.2:3b",
            "context_window": 128000,
            "size_b": 3.2
          }
        ],
        "last_seen": "2026-04-09T12:34:56.789123",
        "last_error": null
      },
      {
        "alias": "mdns-pi5-hailo",
        "base_url": "http://192.168.1.20:8080",
        "source": "mdns",
        "status": "unreachable",
        "slo_state": "unknown",
        "disabled": false,
        "model_count": 0,
        "models": [],
        "last_seen": null,
        "last_error": "Verbindung abgelehnt"
      }
    ],
    "aliases": {
      "default-llm": "ollama-mac/qwen2.5:7b",
      "fast-chat": "ollama-mac/llama3.2:3b"
    }
  }
}
```

### Feldbeschreibungen

**`router`**

| Feld | Typ | Beschreibung |
|---|---|---|
| `version` | string | Router-Schema-Version (aktuell `"1.0.0"`) |
| `alias_count` | int | Anzahl der definierten Aliases |

**`backends[]`**

| Feld | Typ | Beschreibung |
|---|---|---|
| `alias` | string | Eindeutige Backend-Kennung |
| `base_url` | string | Basis-URL des OpenAI-kompatiblen Endpunkts |
| `source` | string | `"static"` (Konfigurationsdatei) oder `"mdns"` (automatisch erkannt) |
| `status` | string | `"ready"` / `"unreachable"` / `"unknown"` |
| `slo_state` | string \| null | `"vision_idle"` / `"vision_active"` / `"unknown"` / `null` |
| `disabled` | bool | `true` wenn aus dem Routing ausgeschlossen |
| `model_count` | int | Anzahl der exponierten Modelle |
| `models[]` | array | Modellliste (`name`, `context_window`, `size_b`) |
| `last_seen` | string \| null | Letzter erfolgreicher Konnektivitätsprüfung (ISO 8601) |
| `last_error` | string \| null | Letzte Fehlermeldung |

**`aliases`**

Eine Zuordnung von logischen Alias-Namen zu physischen Modell-IDs (`backend-alias/model-name`).

---

## POST /api/llm_router/refresh

Erzwingt einen Probe auf allen Backends oder einem angegebenen Backend und aktualisiert `status` und die Modellliste.

### Anfrage

**Zum Aktualisieren aller Backends (kein Körper):**

```
POST /api/llm_router/refresh
Content-Type: application/json

{}
```

Ein leerer Körper ohne Content-Type-Header wird ebenfalls akzeptiert.

**Zum Aktualisieren eines bestimmten Backends nur:**

```json
{
  "alias": "ollama-mac"
}
```

### Antwort `200 OK`

```json
{
  "status": "ok",
  "data": {
    "refreshed": [
      {
        "alias": "ollama-mac",
        "status": "ready",
        "model_count": 3,
        "disabled": false,
        "last_error": null
      },
      {
        "alias": "mdns-pi5-hailo",
        "status": "unreachable",
        "model_count": 0,
        "disabled": false,
        "last_error": "Verbindung abgelehnt"
      }
    ]
  }
}
```

Das `refreshed`-Array enthält nur leichte Aktualisierungsergebnisse (verwenden Sie `/status` für vollständige Details).

### Fehler `404 Not Found`

Wenn ein `alias` angegeben ist, aber nicht vorhanden:

```json
{
  "status": "error",
  "error": "unknown backend: nonexistent-alias"
}
```

### Hinweise

- Probes werden synchron ausgeführt (die Antwort wird nach Abschluss zurückgegeben)
- Probes werden auch für Backends mit `disabled: true` ausgeführt (Status wird weiterhin aktualisiert)
- mDNS-entdeckte Backends sind enthalten

---

## POST /api/llm_router/backends/`<alias>`/disable

Deaktiviert das angegebene Backend. Deaktivierte Backends werden aus dem Routing ausgeschlossen und der Status wird zu `data/llm_router_state.json` persistiert.

### Anfrage

```
POST /api/llm_router/backends/ollama-mac/disable
```

Kein Körper erforderlich.

### Antwort `200 OK`

```json
{
  "status": "ok",
  "data": {
    "alias": "ollama-mac",
    "disabled": true
  }
}
```

### Fehler `404 Not Found`

```json
{
  "status": "error",
  "error": "unknown backend: nonexistent-alias"
}
```

### Fehler `500 Internal Server Error`

Wenn die Persistierung auf der Festplatte fehlschlägt (Berechtigungsfehler, Festplatte voll usw.). Der In-Memory-Status wird zurückgerollt.

```json
{
  "status": "error",
  "error": "failed to persist disabled state"
}
```

### Persistierungsmechanismus

1. Setzen Sie das Flag `disabled` auf `true` im In-Memory-Katalog
2. Atomares Schreiben zu `data/llm_router_state.json` (über `.tmp`-Datei und `os.replace`)
3. Wenn der Schreibvorgang fehlschlägt, wird Schritt 1 zurückgerollt und ein `500` zurückgegeben

Der deaktivierte Status wird über Anwendungsneustarts hinweg beibehalten. Wenn ein mDNS-entdecktes Backend vor dem Start deaktiviert wurde, wird der deaktivierte Status nach der Erkennung automatisch angewendet.

---

## POST /api/llm_router/backends/`<alias>`/enable

Aktiviert das angegebene Backend. Das Gegenteil von `disable`.

### Anfrage

```
POST /api/llm_router/backends/ollama-mac/enable
```

Kein Körper erforderlich.

### Antwort `200 OK`

```json
{
  "status": "ok",
  "data": {
    "alias": "ollama-mac",
    "disabled": false
  }
}
```

### Fehler

Gleich wie der `disable`-Endpunkt (`404` / `500`). Persistiert mit `disabled: false`.

---

## Endpunkt-Zusammenfassung

| Methode | Pfad | Beschreibung |
|---|---|---|
| `GET` | `/api/llm_router/status` | Snapshot aller Backends und Aliases abrufen |
| `POST` | `/api/llm_router/refresh` | Probe auf alle oder einzelne Backends erzwingen |
| `POST` | `/api/llm_router/backends/<alias>/disable` | Backend deaktivieren (persistiert) |
| `POST` | `/api/llm_router/backends/<alias>/enable` | Backend aktivieren (persistiert) |

## Zugehörige Dokumentation

- [LLM Router WebUI Guide](../llm-router/webui.md)
- [LLM Router Setup](../llm-router/setup.md)
