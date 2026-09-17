# Verteilte Inferenz API

REST API für die Registrierung des verteilten Inferenz-Servers. Verteilt CLIP-Semantik-Indexierungsworkloads auf mehrere Knoten mit einer Shared-Queue-Strategie.

## Endpunkte

### GET /api/inference-servers

Gibt die Liste der registrierten Server und den aktuellen Dispatch-Modus zurück.

**Antwort:**

```json
{
  "status": "ok",
  "mode": "single",
  "servers": [
    {
      "id": 1,
      "name": "Hailo Worker 1",
      "endpoint_url": "http://192.168.1.10:9090",
      "inference_types": ["clip"],
      "priority": 50,
      "enabled": true,
      "timeout": 30
    }
  ]
}
```

- `mode`: `"single"` | `"parallel"` | `"idle_first"`
- `servers`: Array von Server-Konfigurationsobjekten

---

### POST /api/inference-servers

Einen neuen Inferenz-Server registrieren.

**Anfragekörper:**

| Feld | Typ | Erforderlich | Standard | Beschreibung |
|---|---|---|---|---|
| `name` | string | ✓ | — | Anzeigename |
| `endpoint_url` | string | ✓ | — | Worker-Basis-URL |
| `inference_types` | string[] | — | `["clip"]` | Unterstützte Inferenztypen |
| `priority` | int | — | `50` | Priorität (niedrigerer Wert = höhere Priorität) |
| `bearer_token` | string | — | — | Authentifizierungs-Token |
| `timeout` | int | — | `30` | Request-Timeout in Sekunden |

**Antwort:**

```json
{
  "status": "ok",
  "server": { ... }
}
```

---

### PUT /api/inference-servers/{server_id}

Aktualisieren Sie die Konfiguration eines bestehenden Servers. Akzeptiert einen Teillörper mit denselben Feldern wie POST.

---

### DELETE /api/inference-servers/{server_id}

Einen Server aus der Registry entfernen.

**Antwort:**

```json
{ "status": "ok" }
```

---

### POST /api/inference-servers/{server_id}/test

Führen Sie eine Gesundheitsprüfung gegen den angegebenen Server durch.

**Antwort:**

```json
{
  "status": "ok",
  "server_id": 1,
  "healthy": true,
  "latency_ms": 12.5
}
```

---

### GET /api/inference-servers/health

Führen Sie Gesundheitsprüfungen gegen alle aktivierten Server gleichzeitig durch.

**Antwort:**

```json
{
  "status": "ok",
  "results": [
    { "server_id": 1, "healthy": true, "latency_ms": 12.5 },
    { "server_id": 2, "healthy": false, "error": "Verbindung abgelehnt" }
  ]
}
```

---

### POST /api/inference-servers/mode

Legen Sie den Dispatch-Modus fest.

**Anfragekörper:**

| Feld | Typ | Erforderlich | Beschreibung |
|---|---|---|---|
| `mode` | string | ✓ | `"single"` \| `"parallel"` \| `"idle_first"` |

**Antwort:**

```json
{ "status": "ok", "mode": "parallel" }
```

---

## Dispatch-Modi

| Modus | Beschreibung |
|---|---|
| `single` | Verwenden Sie nur den Server mit der höchsten Priorität (niedrigster Prioritätswert) |
| `parallel` | Verteilen Sie die Arbeit auf alle aktivierten Server mit einer Shared Queue |
| `idle_first` | Gesundheitsprüfung zuerst, dann Verteilen auf responsive Server nur |

## Verteilte semantische Indexierung

Fügen Sie `distributed: true` zum `POST /api/index/start`-Anfragekörper (Semantic-Search-Erweiterung) hinzu, um verteilte Indexierung mit registrierten Worker-Servern zu aktivieren.

```json
{
  "batch_size": 32,
  "distributed": true
}
```

## Worker-Server-Setup

```bash
python deploy/hailo_tagger_server.py --port 9090
```

Unterstützte Endpunkte:

| Pfad | Beschreibung |
|---|---|
| `GET /health` | Gesundheitsprüfung |
| `POST /tag` | WD-Tagger-Inferenz |
| `POST /clip-encode` | CLIP-Vektorencoding |

## MCP-Tools

| Tool | Beschreibung |
|---|---|
| `inference-servers-list` | Server auflisten und aktuellen Modus abrufen |
| `inference-server-add` | Einen neuen Server registrieren |
| `inference-server-update` | Server-Konfiguration aktualisieren |
| `inference-server-remove` | Einen Server entfernen |
| `inference-server-health` | Gesundheitsprüfungen durchführen |
| `inference-dispatch-mode-set` | Dispatch-Modus festlegen |
