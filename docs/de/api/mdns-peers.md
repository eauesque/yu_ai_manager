# API: /api/mdns (Peer-Erkennung)

> Zielversion: v4.64.0 und später (Hailo-Erweiterungen: v4.66.0 und später)

API für yu_ai_manager-Knoten in einem LAN zur gegenseitigen Erkennung über mDNS (`_yu-ai._tcp.local.`). Es gibt zwei Endpunkte.

---

## GET /api/mdns/identity

### Übersicht

Ein Selbstvorstellungsendpunkt für einen Knoten. Andere Knoten rufen diesen während der Peer-Überprüfung auf, um zu bestätigen, dass die Informationen, die über mDNS angekündigt werden, zu einer echten yu_ai_manager-Instanz gehören.

### Authentifizierung

**Authentifizierungs-Bypass (nicht erforderlich).** Die Authentifizierung wird absichtlich weggelassen, da dieser Endpunkt für gegenseitige Peer-Überprüfung verwendet wird. Die Antwort enthält nur Informationen, die bereits über mDNS öffentlich verfügbar sind. Es sind keine Geheimnisse oder sensiblen Informationen enthalten.

### Antwort

```json
{
  "product": "yu_ai_manager",
  "node_id": "a1b2c3d4-...",
  "version": "4.66.0",
  "capabilities": ["hailo"],
  "hailo_ollama_url": "http://192.168.1.10:11434"
}
```

| Feld | Typ | Beschreibung |
|---|---|---|
| `product` | string | Immer `"yu_ai_manager"` |
| `node_id` | string | Eindeutige UUID des Knotens |
| `version` | string | Anwendungsversion (aus der VERSION-Datei gelesen) |
| `capabilities` | string[] | Liste der verfügbaren Funktionen. Derzeit nur `"hailo"` |
| `hailo_ollama_url` | string (optional) | LAN-Zugriffs-URL für Hailo-Ollama. Nicht enthalten, wenn die LAN-IP nicht bestimmt werden kann |

**Bedingung für `capabilities` zum Einschließen von `"hailo"`:** Das Backend `"hailo-local"` ist im LLM Router-Katalog registriert.

**Bedingung für `hailo_ollama_url` zum Einschließen:** Das Backend `"hailo-ollama-local"` ist im Katalog registriert und eine LAN-IP kann bestimmt werden. Loopback-Adressen (`127.0.0.1` usw.) werden in die LAN-IP umgeschrieben.

---

## GET /api/mdns/peers

### Übersicht

Gibt eine Liste der von diesem Knoten erkannten LAN-Peers zurück. Beabsichtigt für Überprüfungen des mDNS-Subsystem-Status und Debugging.

### Authentifizierung

**Authentifizierungs-Bypass (nicht erforderlich).** Die Antwort enthält nur Informationen, die bereits über mDNS auf dem LAN übertragen werden.

### Antwort (Normal)

```json
{
  "running": true,
  "status": "browsing",
  "self_node_id": "a1b2c3d4-...",
  "peers": [
    {
      "node_id": "e5f6a7b8-...",
      "hostname": "raspberrypi.local",
      "version": "4.66.0",
      "llm_base_url": "http://192.168.1.20:11434",
      "llm_provider": "ollama",
      "capabilities": ["hailo"],
      "web_port": 5000,
      "addresses": ["192.168.1.20"],
      "hailo_ollama_url": "http://192.168.1.20:11434",
      "first_seen": 1712600000.0,
      "last_seen": 1712603600.0
    }
  ]
}
```

| Feld | Typ | Beschreibung |
|---|---|---|
| `running` | bool | Ob das mDNS-Subsystem ausgeführt wird |
| `status` | string | Status-String des Subsystems |
| `self_node_id` | string | Die node_id dieses Knotens |
| `peers` | object[] | Liste der erkannten Peers (siehe Tabelle unten) |

**peers-Elemente:**

| Feld | Typ | Beschreibung |
|---|---|---|
| `node_id` | string | Eindeutige UUID des Peers |
| `hostname` | string | mDNS-Hostname |
| `version` | string | Anwendungsversion des Peers |
| `llm_base_url` | string \| null | LLM-Endpunkt-URL des Peers |
| `llm_provider` | string \| null | LLM-Provider-Name (z.B. `"ollama"`) |
| `capabilities` | string[] | Funktionsliste des Peers |
| `web_port` | int \| null | WebUI-Port des Peers |
| `addresses` | string[] | LAN-IP-Adressen des Peers |
| `hailo_ollama_url` | string \| null | Hailo-Ollama-URL des Peers |
| `first_seen` | float \| null | Erkennung zum ersten Mal (Unix-Zeitstempel) |
| `last_seen` | float \| null | Letzte Verifizierung (Unix-Zeitstempel) |

### Antwort (mDNS nicht initialisiert)

```json
{
  "running": false,
  "reason": "mdns subsystem not initialised (disabled or init failed)",
  "peers": []
}
```

Wenn `running: false`, ist mDNS entweder deaktiviert oder die Initialisierung ist fehlgeschlagen. Überprüfen Sie die Konfiguration und Startprotokolle.

---

## Debug-Modus

Starten Sie yu mit der Umgebungsvariable `TAGDB_DEBUG_TRUSTED_PEERS=1`, um zusätzliche Felder in der Antwort `/api/mdns/peers` einzuschließen.

```json
{
  "running": true,
  "peers": [...],
  "trusted_ips": ["192.168.1.20", "192.168.1.30"],
  "bridge": {
    "managed_aliases": ["ollama-192.168.1.20"],
    "config_aliases": ["my-nas"],
    "cooldown_seconds_remaining": {
      "e5f6a7b8": 12.3
    }
  }
}
```

| Feld | Beschreibung |
|---|---|
| `trusted_ips` | Liste der in der Registry der vertrauenswürdigen IPs registrierten IPs |
| `bridge.managed_aliases` | Liste der vom mDNS-Bridge verwalteten Aliases |
| `bridge.config_aliases` | Liste der in der Konfiguration statisch definierten Aliases |
| `bridge.cooldown_seconds_remaining` | Verbleibende Cooldown-Sekunden mit Schlüssel nach den ersten 8 Zeichen der node_id |

**Warnung:** `trusted_ips` könnte als Angriffsziel-Liste dienen, daher ist es standardmäßig nicht verfügbar. Setzen Sie `TAGDB_DEBUG_TRUSTED_PEERS=1` nicht in Produktionsumgebungen.

---

## mDNS-Ermittlungsfluss

```
Anderer Knoten startet
    │
    ▼
Sendet mDNS _yu-ai._tcp.local.
    │
    ▼
LlmRouterMdnsBridge empfängt on_peer_added()
    │
    ▼
HTTP-Überprüfung über GET /api/mdns/identity
    │
    ├─ Erfolg → In PeerRegistry / BackendCatalog registrieren
    └─ Fehler → Nach Cooldown erneut versuchen
```

---

## Zugehörige Dateien

- `routes/mdns_identity.py` -- Endpunkt-Implementierung
- `core/mdns/` -- mDNS-Dienst / Adressen-Dienstprogramme
- `core/llm_router/state.py` -- BackendCatalog
- `core/web/trusted_peer_registry.py` -- Registry der vertrauenswürdigen IPs
- `docs/en/mesh-inference/overview.md` -- Gesamte Mesh-Inferenz-Architektur
