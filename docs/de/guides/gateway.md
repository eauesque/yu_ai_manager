# Gateway — LAN-Authentifizierungsgrenze-Leitfaden

> Zielversion: Gateway Phase 1 (v4.75.0+) / Gradio-Unterstützung hinzugefügt (v4.255.11+)

## Was ist Gateway?

Gateway ist ein Reverse-Proxy, der den Zugriff auf **Backend-Tools ohne Authentifizierungsfunktion**
wie SD WebUI, ComfyUI, Ollama und Gradio-Anwendungen durch **Bearer-Token + Scope-Modell** einheitlich schützt.

```
Externe Clients / Separate Maschine im LAN
    │
    │  Authorization: Bearer <api_key>
    ▼
 yu_ai_manager  (/v1/*, /sd/*, /comfy/*, /gradio/<name>/*)
 ┌────────────────────────────────────────────────────────┐
 │                      Gateway                          │
 │          Scope-Prüfung ──► Backend-Auswahl           │
 └────────────────────────────────────────────────────────┘
    │          │            │            │
    ▼          ▼            ▼            ▼
 Ollama    SD WebUI     ComfyUI      Gradio
 :11434     :7860         :8188        :7861
```

### Unterschied zu LLM Router

| | Gateway | LLM Router |
|---|---|---|
| **Ziel** | SD WebUI, ComfyUI, Ollama, Gradio zusammen | Nur LLM (Ollama) |
| **Authentifizierung** | Scope-basierter Bearer erforderlich | Loopback kann umgangen werden |
| **Proxy-Ziele** | `/sd/*`, `/comfy/*`, `/v1/*`, `/gradio/<name>/*` | Nur `/v1/*` |
| **Hauptverwendung** | Generierungstools sicher extern/im LAN bereitstellen | Backend für AI-Coding-Tools |

Beide können auf derselben Maschine aktiviert werden.

---

## Einrichtung

### 1. Ersten API-Schlüssel erstellen (CLI)

```bash
uv run python -m core.gateway.cli create-key --id admin-local --scopes "*"
```

Beispielausgabe:
```
id:      admin-local
secret:  gw_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
(Dieser Secret wird nur einmal angezeigt. Bitte sofort kopieren.)
```

### 2. Konfiguration in config.json hinzufügen

```json
{
  "gateway": {
    "auth": {
      "mode": "api_key",
      "allow_loopback_bypass": true,
      "api_keys": [
        {
          "id": "admin-local",
          "secret_enc": "enc:v2:...",
          "scopes": ["*"],
          "allowed_models": null
        }
      ]
    },
    "backends": {
      "ollama":       {"type": "ollama",   "base_url": "http://127.0.0.1:11434"},
      "sd_webui":     {"type": "sd_webui", "base_url": "http://127.0.0.1:7860"},
      "comfyui":      {"type": "comfyui",  "base_url": "http://127.0.0.1:8188", "ws_url": "ws://127.0.0.1:8188/ws"},
      "irodori-tts":  {"type": "gradio",   "base_url": "http://127.0.0.1:7861"}
    },
    "health_probe": {"enabled": true, "interval_seconds": 10}
  }
}
```

> Für das Feld `secret_enc` den verschlüsselten Wert im Format `enc:v2:...` aus der CLI-Ausgabe verwenden.  
> Klartext-Secrets dürfen nicht direkt in `config.json` geschrieben werden.

### 3. App neu starten und Funktion überprüfen

```bash
GW_HOST=<LAN-IP dieser Maschine>
GW_PORT=5000
BEARER=<api-key-secret>

# Ohne Authentifizierung → 401
curl -i http://$GW_HOST:$GW_PORT/v1/models

# Mit korrektem Bearer → 200
curl http://$GW_HOST:$GW_PORT/v1/models \
  -H "Authorization: Bearer $BEARER"

# Backend-Verfügbarkeit
curl http://$GW_HOST:$GW_PORT/v1/router/capabilities \
  -H "Authorization: Bearer $BEARER"

# Node-Dienste-Liste
curl http://$GW_HOST:$GW_PORT/v1/node/services \
  -H "Authorization: Bearer $BEARER"
```

---

## WebUI (/gateway-Seite)

Verwaltungs-Dashboard unter `/gateway`.

### Backend-Liste

Zeigt den Betriebsstatus der registrierten Backends.

| Spalte | Beschreibung |
|---|---|
| **Typ** | Backend-Typ (`ollama`, `sd_webui`, `comfyui`, `gradio`) |
| **Port** | Portnummer des Proxy-Ziels |
| **Status** | `online` / `offline` / `unknown` |
| **Aktionen** | Probe (Verbindungstest), Einstellungen |

### Automatischer Backend-Scan

Durch Klicken auf „Scan" werden gängige lokale Ports (7860, 8188, 11434, 7861 usw.)  
gescannt und laufende Tools automatisch erkannt und zur Registrierung vorgeschlagen.

### API-Schlüssel-Verwaltung

API-Schlüssel können auch über die WebUI hinzugefügt und widerrufen werden (Schlüssel mit `*`-Scope erforderlich).

---

## Scope-Referenz

| Scope | Erlaubte Endpunkte |
|---|---|
| `llm:chat` | `POST /v1/chat/completions` |
| `llm:messages` | `POST /v1/messages` (Anthropic-kompatibel) |
| `llm:models` | `GET /v1/models` |
| `sd:generate` | `POST /sd/sdapi/v1/txt2img` usw. |
| `sd:query` | `GET /sd/sdapi/v1/samplers` usw. |
| `sd:admin` | `POST /sd/sdapi/v1/options` usw. |
| `comfy:generate` | `POST /comfy/api/prompt` usw. |
| `comfy:query` | `GET /comfy/api/queue` usw. |
| `memory:read` | `GET /agentmemory/memories` usw. (Lesen) |
| `memory:write` | `POST /agentmemory/observe` usw. (Schreiben) |
| `memory:admin` | `POST /agentmemory/migrate` usw. (Verwaltung) |
| `ollama:proxy` | `GET/POST /ollama/<name>/*` (Ollama native API + OpenAI-kompatibel, vollständig transparent) |
| `gradio:proxy` | `GET/POST /gradio/<name>/*` (vollständig transparent) |
| `gateway:admin` | API-Schlüssel-Verwaltung und Konfigurationsänderungen (automatisch für Loopback) |
| `node:status` | `GET /v1/node/services` |
| `*` | Alle Scopes (nur für Administratoren) |

### Beispielschlüssel nach Anwendungsfall

```json
"api_keys": [
  {
    "id": "claude-code",
    "secret_enc": "enc:v2:...",
    "scopes": ["llm:chat", "llm:messages", "llm:models"],
    "allowed_models": null
  },
  {
    "id": "comfy-client",
    "secret_enc": "enc:v2:...",
    "scopes": ["comfy:generate", "comfy:query"],
    "allowed_models": null
  }
]
```

---

## Ollama-Proxy

Ein transparenter Proxy für die vollständige Ollama-API — sowohl nativ (`/api/*`) als auch OpenAI-kompatibel (`/v1/*`) —  
getrennt vom LLM Router `/v1/*`. `OLLAMA_HOST` auf Gateway setzen, um Authentifizierung hinzuzufügen.

### Proxy-URL

```
/ollama/<backend_name>/<subpath>  →  registrierte base_url/<subpath>
```

### Konfigurationsbeispiel

```json
"backends": {
  "ollama": {"type": "ollama", "base_url": "http://127.0.0.1:11434"}
}
```

### Client-Einrichtung (`OLLAMA_HOST`)

```bash
export OLLAMA_HOST=http://<gateway-host>:5000/ollama/ollama
# Alle nachfolgenden ollama-Befehle laufen über Gateway
ollama list
ollama run llama3.3:70b
```

> Clients, die keinen Bearer-Token übergeben können, können `allow_loopback_bypass: true` über Loopback nutzen  
> oder einen Schlüssel mit `*`-Scope als Workaround verwenden.

### Große Dateiübertragungen

Modell-Blobs (`/api/blobs/*`) werden gestreamt ohne Timeout (andere Pfade: 300 s).  
GB-große Modell-Pulls und -Pushes funktionieren problemlos.

---

## Gradio-Proxy

Ermöglicht Zugriff auf Gradio-basierte WebUIs (z. B. Irodori-TTS) über Gateway mit Bearer-Authentifizierung.  
Minimale Implementierung: vollständig transparent mit nur 50 MiB Body-Limit (keine Endpunkt-Beschränkungen).

### Proxy-URL

```
/gradio/<backend_name>/<subpath>  →  registrierte base_url/<subpath>
```

`<backend_name>` muss einem Schlüssel im Abschnitt `backends` in `config.json` entsprechen.

### Konfigurationsbeispiel

```json
"backends": {
  "irodori-tts": {"type": "gradio", "base_url": "http://127.0.0.1:7861"}
}
```

### Überprüfung

```bash
GW=http://localhost:5000
KEY=<api-key-secret>

# Gradio-App-Root
curl -H "Authorization: Bearer $KEY" "$GW/gradio/irodori-tts/"

# Gradio 3.x predict
curl -H "Authorization: Bearer $KEY" \
  -X POST "$GW/gradio/irodori-tts/run/predict" \
  -H "Content-Type: application/json" \
  -d '{"data": ["Hello"], "fn_index": 0}'
```

### Einschränkungen

- WebSocket (`/queue/join`) wird nicht unterstützt — nur HTTP
- Gradio 4.x SSE-Streams (`GET /call/{api_name}/{event_id}`) werden vollständig gepuffert,  
  was bei langen Generierungen (Video usw.) zu Timeouts führen kann

---

## Agent Memory (agentmemory) Proxy

Gateway bietet auch einen Proxy für `@agentmemory/mcp` und andere agentmemory-Clients  
für sicheren Zugriff über LAN.

### Endpunkte

```
/agentmemory/livez       → Keine Authentifizierung erforderlich (Health-Check)
/agentmemory/health      → Erfordert memory:read-Scope
/agentmemory/memories    → memory:read
/agentmemory/observe     → memory:write
/agentmemory/migrate     → memory:admin
...（vollständige Liste siehe agentmemory offizielle API）
```

### Gleiche Maschine

Mit `allow_loopback_bypass: true` umgehen Loopback-Anfragen (127.0.0.1) die Authentifizierung vollständig.  
Keine Änderungen an der MCP-Konfiguration erforderlich.

### Remote-Maschine (LAN)

`@agentmemory/mcp` liest die Umgebungsvariable `AGENTMEMORY_SECRET`  
und sendet sie als `Authorization: Bearer <secret>` upstream.

**MCP-Konfigurationsbeispiel (`claude_desktop_config.json` / `.mcp.json`):**

```json
{
  "agentmemory": {
    "command": "npx",
    "args": ["-y", "@agentmemory/mcp"],
    "env": {
      "AGENTMEMORY_URL": "http://<gateway-host>:5000/agentmemory",
      "AGENTMEMORY_SECRET": "<api-key-secret>"
    }
  }
}
```

Erforderliche Scopes (beim Erstellen des Schlüssels angeben):

```json
"scopes": ["memory:read", "memory:write"]
```

`memory:admin` hinzufügen, wenn Migrations- oder Governance-Endpunkte benötigt werden.

### Überprüfung

```bash
GW=http://<gateway-host>:5000
KEY=<api-key-secret>

# Keine Authentifizierung erforderlich (livez)
curl $GW/agentmemory/livez

# Memories mit Bearer abrufen
curl -H "Authorization: Bearer $KEY" "$GW/agentmemory/memories?limit=3"

# Basic-Authentifizierung funktioniert ebenfalls (SD-Client-kompatibel)
curl -u "user:$KEY" "$GW/agentmemory/health"
```

---

## Authentifizierungsmodi

| Modus | Verhalten |
|---|---|
| `api_key` | Bearer-Token erforderlich (`allow_loopback_bypass: true` befreit nur Loopback) |
| `loopback` | Keine Authentifizierung von Loopback (127.0.0.1). LAN erfordert `api_key`-Äquivalent |
| `none` | Keine Authentifizierung (nur für Entwicklung/Tests, nicht für Produktion) |

Mit `allow_loopback_bypass: true` können Tools auf derselben Maschine  
(z. B. Claude Code CLI) Gateway ohne API-Schlüssel passieren.

---

## Health Probe

Bei `health_probe.enabled: true` werden Backends automatisch  
im konfigurierten Intervall geprüft.

```json
"health_probe": {
  "enabled": true,
  "interval_seconds": 10
}
```

Offline-Backends werden als `"status": "offline"`  
in der `/v1/router/capabilities`-Antwort gemeldet.

---

## Häufige Probleme

| Symptom | Ursache / Lösung |
|---|---|
| Alle Anfragen geben 401 zurück | `allow_loopback_bypass` ist `false`, sodass auch Loopback einen Schlüssel benötigt. Oder Bearer-Wert ist falsch |
| SD WebUI-Proxy gibt 404 zurück | Falscher Port in `sd_webui.base_url` (Standard: 7860). Probe von `/gateway` ausführen |
| ComfyUI WebSocket verbindet nicht | `ws_url` konfiguriert prüfen (`ws://127.0.0.1:8188/ws`) |
| Gradio-Proxy gibt 404 zurück | `<backend_name>` muss dem Schlüssel in `config.json`-Backends entsprechen. Auch `"type": "gradio"` erforderlich |
| Gradio SSE-Stream läuft auf Timeout | Vollpuffer-Einschränkung für lange Generierungen (Video usw.). Kurze Aufgaben (TTS usw.) sind nicht betroffen |
| 403 bei unzureichenden Scopes | API-Schlüssel hat nicht genug Scopes. Neue Schlüssel über API-Schlüssel-Verwaltung mit `*`-Scope-Schlüssel hinzufügen |
| Bestimmte Modelle über `allowed_models` einschränken | Als Array angeben: `"allowed_models": ["qwen2.5:7b", "llama3.3:70b"]` |

---

## Non-Goals (Phase-1-Umfang)

- Backend-Start/Stop/Neustart (über SSH + systemctl)
- `/v1/responses` (Codex-kompatibler Facade) — Phase 2+
- Lastverteilung über mehrere Gateway-Instanzen — LAN Cowork Distributed Inference verwenden

---

## Verwandte Dokumentation

- [Gateway API-Referenz](../api/gateway.md) — Details zu `/api/gateway/*`-Endpunkten
- [LLM Router Einrichtung](../llm-router/setup.md) — Leichtgewichtiger LLM-only-Proxy
- [LAN Cowork Übersicht](../lan-cowork/README.md) — Multi-Node-Koordination

## API-Schlüssel-Verwaltung über WebUI

Über die Registerkarte **„Gateway API-Schlüssel"** auf der Einstellungsseite können Schlüssel erstellt, aufgelistet und gelöscht werden.  
Ein Link ist auch auf der [Gateway-Seite](/gateway) verfügbar.

### API-Schlüssel erstellen

1. **Label** eingeben (Beispiel: `Claude Desktop`) — ID wird automatisch als Slug generiert (Beispiel: `claude-desktop`)
2. **Scopes** über Badges auswählen (mindestens einer erforderlich)
3. Bei Auswahl von `*` (Vollzugriff) das Bestätigungs-Kontrollkästchen aktivieren
4. Auf **Erstellen** klicken und Secret kopieren — **wird nach dem Verlassen dieser Seite nie mehr angezeigt**

### Hinweise

- Der letzte Schlüssel mit `*`-Scope kann nicht gelöscht werden (verhindert Bearer-Lockout)
- Zuerst einen anderen `*`-Schlüssel erstellen, bevor der alte gelöscht wird

### Verwendung

```bash
curl -H "Authorization: Bearer <secret>" http://localhost:5000/v1/chat/completions ...
```
