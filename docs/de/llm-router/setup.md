# LLM Router Setup

## Hinzufügen zu config.json

```json
{
  "llm_router": {
    "enabled": true,
    "auth": {
      "mode": "loopback",
      "api_key": "",
      "allow_loopback_bypass": true
    },
    "backends": [
      {
        "alias": "ollama-local",
        "base_url": "http://localhost:11434/v1",
        "type": "ollama",
        "auto_discover": true
      }
    ],
    "aliases": {
      "local-fast": "ollama-local/qwen2.5:7b",
      "local-coder": "ollama-local/qwen2.5-coder:32b"
    }
  }
}
```

## Integration mit Claude Code

```bash
ANTHROPIC_BASE_URL=http://localhost:5000/v1 claude
```

Bei Anfragen geben Sie einen Alias oder physischen Namen im Feld `model` an:
- `local-fast` (Alias)
- `ollama-local/qwen2.5:7b` (physischer Name)

## Integration mit Continue (VSCode)

`config.json`:
```json
{
  "models": [
    {
      "title": "Local Coder",
      "provider": "openai",
      "apiBase": "http://localhost:5000/v1",
      "model": "local-coder",
      "apiKey": "dummy"
    }
  ]
}
```

## Knoten-Auto-Discovery -- `.local` Hostname-Unterstützung (Home LAN)

Wenn mehrere Maschinen auf einem Home LAN ausgeführt werden (z. B. Mac mini + Pi5 + Windows GPU Machine), können Sie `.local`-Hostnamen anstelle von IP-Adressen in `base_url` verwenden. Dies bedeutet, dass **die Konfiguration weiterhin funktioniert, selbst wenn DHCP IP-Adressen neu zuweist**. Es ist keine zusätzliche Implementierung auf der yu_ai_manager-Seite erforderlich -- `httpx` löst Namen automatisch über den Betriebssystem-Resolver (Bonjour / Avahi / mDNSResponder) auf.

```json
{
  "llm_router": {
    "enabled": true,
    "backends": [
      { "alias": "ollama-mac", "base_url": "http://mac-mini.local:11434/v1", "type": "ollama" },
      { "alias": "ollama-pi5", "base_url": "http://pi5.local:11434/v1",      "type": "ollama" },
      { "alias": "ollama-win", "base_url": "http://gpu-rig.local:11434/v1",  "type": "ollama" }
    ],
    "aliases": {
      "local-fast":  "ollama-mac/qwen2.5:7b",
      "local-coder": "ollama-pi5/qwen2.5-coder:32b",
      "local-big":   "ollama-win/llama3.3:70b"
    }
  }
}
```

Beispiel: [`config.example.local-hostname.json`](../../../config.example.local-hostname.json)

### Anforderungen

| Betriebssystem | Erforderlich |
|---|---|
| macOS | Bonjour (integriert, keine zusätzliche Installation erforderlich) |
| Linux | `avahi-daemon` (`sudo apt install avahi-daemon` / `sudo systemctl enable --now avahi-daemon`) |
| Windows 10/11 | mDNSResponder (Win10 1803 und später können `.local` nativ auflösen. Falls nicht funktioniert, installieren Sie Bonjour Print Services) |

### Überprüfung

```bash
# Überprüfen Sie, dass die Auflösung funktioniert
python -c "import socket; print(socket.gethostbyname('mac-mini.local'))"
# → Falls es 192.168.x.x zurückgibt, funktioniert es
```

### Subnetzübergreifend / Unternehmens-LAN / VPN

mDNS funktioniert über L2-Multicast, daher **kann es Router, VPNs oder isolierte VLANs in Unternehmensnetzen nicht erreichen**. Geben Sie in diesen Umgebungen IP-Adressen direkt an wie zuvor:

```json
"backends": [
  { "alias": "remote-gpu", "base_url": "http://10.20.30.40:11434/v1", "type": "ollama" },
  { "alias": "tailscale-mac", "base_url": "http://100.x.x.x:11434/v1", "type": "ollama" }
]
```

Falls Sie einen mDNS-Reflektor in einer VLAN-segmentierten Umgebung benötigen, wenden Sie sich an Ihren LAN-Administrator. yu_ai_manager bietet keinen mDNS-Reflektor oder Proxy.

### Bekannte Einschränkungen

- **Windows mDNS-Auflösung kann gelegentlich langsam sein** (~1 Sekunde): Es wird empfohlen, den Backend-`timeout` auf 3 Sekunden oder mehr zu setzen
- **`.local`-Suffix ist erforderlich**: Wenn Sie nur `mac-mini` verwenden, fällt es auf NetBIOS / DNS zurück, schreiben Sie also immer `mac-mini.local`
- **Ollama bewirbt sich nicht über mDNS**: Nur Hostname-Auflösung wird verwendet; der Port (11434) muss manuell angegeben werden. Für mit yu kolokalisiertes Ollama fügt v4.71.0 einen `_ollama._tcp.local.` Advertiser auf der yu-Seite hinzu. Für reines nacktes Ollama ohne yu siehe "Verarbeitung reiner nackter Ollama-Knoten (ohne ko-gehostetes yu)" unten für die Richtlinie

## Umgebungsvariablen

| Variable | Verhalten |
|---|---|
| `TAGDB_DISABLE_LLM_ROUTER` | Setzen Sie auf `1`, um den gesamten Router zu deaktivieren |
| `TAGDB_DISABLE_LLM_ROUTER_REFRESH` | Setzen Sie auf `1`, um die 5-Minuten-Aktualisierungsschleife zu deaktivieren |
| `TAGDB_LLM_ROUTER_AUTH_MODE` | Überschreiben Sie mit `none`/`loopback`/`api_key` |

## Mehrsprachige Dokumentation

Nach den `docs/ reading rules` in CLAUDE.md werden `en/zh-tw/zh-cn/ko` Versionen basierend auf der `ja/` Quelle synchronisiert (als separate Aufgabe nach der Implementierung; siehe TODO.md).

## Knoten-Auto-Discovery (Phase B -- v4.64.0 und später)

yu_ai_manager Knoten auf dem gleichen LAN entdecken sich automatisch gegenseitig über mDNS (`_yu-ai._tcp.local.`). Auch ohne manuelles Schreiben von Backends in `config.json` werden entdeckte Knoten automatisch im `BackendCatalog` mit `mdns-<prefix>` Aliasen registriert.

### Funktionsweise

1. Beim Start advertiert `core/mdns/` `_yu-ai._tcp.local.`
2. Es abonniert TXT-Datensätze anderer Knoten und überprüft, dass erforderliche Schlüssel (Version/node_id/llm_base_url) vorhanden sind
3. Für Knoten mit einer übereinstimmenden Hauptversion sendet es ein HTTP GET zu `http://<addr>:<web_port>/api/mdns/identity`, um zu bestätigen, dass Produkt/node_id/Version übereinstimmen
4. Verifizierte Knoten werden im LLM Router als `BackendInfo(alias="mdns-<node_id[:8]>")` registriert
5. Von dort aus werden periodische Aktualisierungen durch die vorhandene Probe-Schleife behandelt

### Voraussetzungen

- Der OS mDNS-Responder muss ausgeführt werden (macOS: Bonjour, Linux: Avahi, Windows: mDNSResponder)
- Knoten müssen sich auf dem gleichen L2-Subnetz befinden (für Szenarien über Router / VPN verwenden Sie die manuelle Konfiguration aus Phase A)
- UDP 5353 muss durch die lokale Firewall erlaubt sein
- **Ollama muss dem LAN ausgesetzt sein** -- Ollama bindet standardmäßig an `127.0.0.1:11434`, daher ist es von anderen Knoten im LAN nicht erreichbar. Setzen Sie die Umgebungsvariable `OLLAMA_HOST=0.0.0.0:11434` vor dem Start von Ollama (macOS: `launchctl setenv OLLAMA_HOST "0.0.0.0:11434"`, Linux: systemd unit / `.bashrc`, Windows: Systemumgebungsvariablen). Falls dies nicht gesetzt ist, bestimmt yu_ai_manager, dass es nur localhost ist und advertiert `llm_base_url` nicht (eine Warnung wird im Startprotokoll angezeigt)

### Ollama Auto-Erkennung

Wenn kein localhost-Eintrag in `llm_router.backends` in `config.json` vorhanden ist, sucht yu_ai_manager beim Start in der folgenden Reihenfolge nach Ollama:

1. `http://<LAN_IP>:11434/api/tags` -- Ollama erreichbar vom LAN
2. `http://localhost:11434/api/tags` -- Auch wenn erkannt, wird eine LAN-Ankündigung nicht durchgeführt (die obige Warnung wird angezeigt)

Falls eine 200-Antwort von der LAN IP zurückkommt, wird sie automatisch als `llm_base_url` im TXT-Datensatz aufgenommen. Dies ist für eine konfigurationsfreie Teilnahme von mit Ollama ko-gehosteten Knoten über mDNS vorgesehen. Nicht-Standardports (11435, usw.) oder lmstudio / llamacpp erfordern explizite Einträge in `config.json`.

### Verarbeitung reiner nackter Ollama-Knoten (ohne ko-gehostetes yu) (Richtlinie)

Reine nackte Ollama-Knoten, wo `yu_ai_manager` **nicht** läuft (z. B. ein Mac eines Familienmitglieds, auf dem nur Ollama installiert ist, oder ein Ollama-Container auf einem NAS) sind **nicht von Auto-Discovery abgedeckt**. `Ollama` selbst hat kein Feature, das `_ollama._tcp.local.` offiziell bewirbt, daher gibt es strukturell keine Möglichkeit, sie zu erkennen.

Um solche Knoten vom LLM Router zu verwenden, konfigurieren Sie sie **manuell** über eine der folgenden Methoden:

```json
{
  "llm_router": {
    "backends": [
      { "alias": "ollama-nas",    "base_url": "http://nas.local:11434/v1",     "type": "ollama" },
      { "alias": "ollama-family", "base_url": "http://192.168.1.42:11434/v1", "type": "ollama" }
    ]
  }
}
```

- Falls Ihre Umgebung `.local` Hostnamen unterstützt (siehe "Knoten-Auto-Discovery -- `.local` Hostname-Unterstützung" oben), bevorzugen Sie diese
- Ansonsten hardcodieren Sie die feste IP

#### Warum Auto-Discovery nicht versucht wird

Bei der Gestaltung dieser (2026-04-11) wurden die folgenden drei Optionen verglichen, und Option (c) manuelle Konfigurationsanleitung wurde gewählt:

| Option | Beschreibung | Entscheidung |
|---|---|---|
| (a) Scan des gesamten LANs `:11434` beim Start | Brute-Force-Probe aller Hosts im Subnetz | **Abgelehnt** -- hohe Netzwerklast, störend auf Unternehmens- / großen LANs, kann mit Port-Scanning verwechselt werden, widerspricht der Edge-First-Philosophie |
| (b) Externer Ollama-Advertiser Daemon | Versand eines leichtgewichtigen yu-bereitgestellten Advertisers, der neben jedem Ollama-Host läuft | **Abgelehnt** -- erfordert einen zusätzlichen residenten Prozess, was gleichbedeutend ist mit der Installation von `yu_ai_manager` selbst. Verfehlt den Zweck von "reiner nackter" |
| (c) Manuelle Backend-Konfiguration über feste IP / `.local` | Hand geschriebene Einträge in `config.json` | **Gewählt** -- null zusätzliche Implementierung, explizites Verhalten, vermeidet, Benutzer in unbeabsichtigte Scans zu ziehen |

Falls Ollama Upstream später `_ollama._tcp.local.` offiziell bewirbt oder einen offiziellen Service-Discovery-Mechanismus hinzufügt, werden wir dies als Phase D zu diesem Zeitpunkt erneut überprüfen.

### Deaktivierung

Sie können Auto-Discovery in Umgebungen deaktivieren, wo sie nicht benötigt wird (Docker-Isolation, Unternehmens-LAN, CI, usw.):

- Fügen Sie `"mdns": {"enabled": false}` zu `config.json` hinzu
- Oder setzen Sie die Umgebungsvariable `YU_AI_MDNS_DISABLED=1`

### Bekannte Verhaltensweisen

- **Multi-homed Umgebungen (Wi-Fi + Ethernet)**: Mit der Standardeinstellung (`bind_address: null`) erfolgt die Ankündigung auf beiden Schnittstellen und `PeerInfo.addresses` enthält mehrere IPs. Um sich auf eine einzelne Schnittstelle zu beschränken, geben Sie `"bind_address": "192.168.x.y"` an.
- **Alias-Kollision**: Falls ein Backend in `config.json` einen Alias im `mdns-xxxxxxxx`-Format verwendet, hat die manuelle Konfiguration Priorität und der mDNS-entdeckte Eintrag wird übersprungen.
- **Subnetzübergreifend**: mDNS funktioniert standardmäßig nur innerhalb der L2-Broadcast-Domäne. Für subnetzübergreifend Betrieb verwenden Sie den `.local` Hostname-Ansatz aus Phase A.
- **Sicherheit**: mDNS selbst hat keine Authentifizierung. Es ist für vertrauenswürdige Umgebungen wie Home LANs konzipiert. Deaktivierung wird in öffentlichem Wi-Fi oder großen gemeinsamen Netzwerken empfohlen. Die `/api/mdns/identity` Verifikation verhindert versehentliche Missidentifikation von Knoten oder Mischung mit inkompatiblen älteren Versionen.
