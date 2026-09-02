# Hailo LLM Auto-discovery

**Unterstützte Version**: v4.66.0 und später

## Übersicht

yu_ai_manager kann LLM-Endpunkte, die auf der Hailo NPU des Pi5 laufen, automatisch ermitteln und verwenden, ohne `config.json` zu bearbeiten. Schließen Sie einfach einen Pi5 an das LAN an, und andere yu_ai_manager-Knoten können das Hailo LLM aufrufen.

## Zwei Endpunkttypen

| Endpunkt | Beschreibung | Standard-URL-Muster |
|---|---|---|
| **yu extension Hailo LLM** | OpenAI-kompatibles LLM, bereitgestellt durch die integrierte `builtin-hailo-genai`-Erweiterung in yu_ai_manager | `http://<host>:<yu-port>/ext/hailo-genai/v1/` |
| **hailo-ollama** | OpenAI-kompatibles LLM, bereitgestellt durch die externe Binärdatei `/usr/bin/hailo-ollama` (Standard-Port `:8000`) | `http://<host>:8000/v1/` |

Beide können gleichzeitig laufen und beide werden automatisch registriert. Mit HailoRT 5.3.0+ und `HAILO_OLLAMA_VDEVICE_GROUP_ID=YU_SHARED` gesetzt, teilt der HailoRT-Scheduler das physische Gerät über Round-Robin, sodass es beim gleichzeitigen Verwenden beider zu keinen Konflikten kommt.

## Lokale Auto-Registrierung (Phase A)

Beim Start erkennt yu_ai_manager unabhängig die folgenden zwei Endpunkte:

1. **yu extension**: Wenn `hailo_platform.genai.LLM` importierbar ist und entweder `/dev/hailo0` oder `/dev/h1x-0` existiert, wird es automatisch als `hailo-local`-Backend im Katalog registriert
   (v4.66.1 fügte Unterstützung für Raspberry Pi 5 + AI HAT + HailoRT 5.3.0 hinzu, das das Gerät als `/dev/h1x-0` verfügbar macht)
2. **hailo-ollama**: Eine HTTP-Probe wird an `localhost:8000/v1/models` gesendet (2-Sekunden-Timeout). Wenn eine 200-Antwort empfangen wird, wird sie automatisch als `hailo-ollama-local`-Backend registriert

Wenn ein Backend mit demselben Alias bereits in `llm_router.backends` in `config.json` existiert, hat diese Konfiguration Priorität (sie wird nicht überschrieben).

## mDNS-Ankündigung (Phase B)

Basierend auf den Erkennungsergebnissen der Phase A kündigt yu_ai_manager Hailo-Fähigkeiten gegenüber anderen Knoten über mDNS TXT-Datensätze an:

- `capabilities=llm,hailo` -- Zeigt an, dass die yu extension verfügbar ist
- `hailo_ollama_url=http://192.168.1.10:8000/v1/` -- Nur enthalten, wenn hailo-ollama läuft (neu geschrieben zu einer vom LAN erreichbaren IP)

Wenn andere yu_ai_manager-Knoten dies über mDNS erhalten, führen sie eine Identitätsverifikation über den `/api/mdns/identity`-Endpunkt durch und registrieren automatisch zusätzliche Backends mit den folgenden Aliasen:

- `mdns-<node_id[:8]>-hailo` -- yu extension Hailo LLM (wenn `capabilities` `hailo` enthält, wird die URL aus der `web_port` des Peers + Adressen abgeleitet)
- `mdns-<node_id[:8]>-hailo-ollama` -- Externes hailo-ollama (wenn `hailo_ollama_url` angekündigt wird, wird die URL aus dem TXT-Datensatz verwendet)

## Konfiguration

Standardmäßig aktiviert. Sie können es in `config.json` wie folgt deaktivieren:

```json
{
  "llm_router": {
    "hailo_ollama": {
      "enabled": false,
      "port": 8000
    }
  }
}
```

- **`enabled`**: Setzen Sie auf `false`, um die automatische hailo-ollama-Erkennung vollständig zu deaktivieren. Die Erkennung der yu extension wird separat gesteuert (automatisch bestimmt, ob die Erweiterung geladen ist)
- **`port`**: Portnummer für hailo-ollama (Standard 8000). Werte außerhalb des Bereichs 1-65535 fallen mit einer Warnung zurück auf den Standard

## Sicherheitshinweise

**hailo-ollama hat keine Authentifizierung**. Wenn über mDNS angekündigt, **kann jeder Knoten im LAN frei die Inferenzressourcen von hailo-ollama nutzen**.

| Endpunkt | Authentifizierung | Effektive LAN-Exposition |
|---|---|---|
| yu extension (`/ext/hailo-genai/v1/`) | yu's Web-Auth-Kette (PIN/Session/API-Schlüssel) | Nur Clients authentifiziert mit yu |
| hailo-ollama (`hailo_ollama_url`) | **Keine** | **Alle Knoten im LAN** |

Für Umgebungen außer home LANs oder vertrauenswürdigen VLANs (z. B. öffentliches Wi-Fi) deaktivieren Sie die automatische Ankündigung mit `hailo_ollama.enabled: false`.

## Anzeige in der LLM Router WebUI

Automatisch registrierte Backends werden auf dem `/llm-router`-Dashboard angezeigt (v4.65.0):

- `hailo-local` / `hailo-ollama-local` -- Lokal erkannt (Quelle: `static` Badge)
- `mdns-<id>-hailo` / `mdns-<id>-hailo-ollama` -- Via mDNS erkannt (Quelle: `mdns` Badge)

Alle können vorübergehend über die Deaktivierungsschalter deaktiviert werden. Der deaktivierte Status wird in `data/llm_router_state.json` beibehalten und nach Neustarts beibehalten (implementiert in v4.65.0).

## Sicherheit vor Fehlalarmen

Die Phase-A-Erkennung hat zwei Sicherheitsmechanismen:

1. **Vermeidung von Self-Probes**: Wenn `hailo_ollama.port` auf denselben Wert wie yu's eigener Web-Port gesetzt ist, wird die Probe vollständig übersprungen (verhindert, dass yu sich selbst als hailo-ollama missidentifiziert)
2. **Priorität bestehender Backends**: Wenn ein Backend mit derselben `localhost:<port>/v1` bereits in `config.json` registriert ist, wird die Probe übersprungen, um die Absicht des Benutzers zu respektieren

## TODO Verbleibende Punkte

- (P3) Mehrsprachige Übersetzungen (`en`, `zh-tw`, `zh-cn`, `ko`) -- geplant zusammen mit der v4.65.0 LLM Router WebUI Übersetzungs-Warteschlange
- (P3) Pi5-Integrationstests -- Playwright 16-Element-Äquivalent in einer 2-Knoten-Einrichtung
- (P3) IPv6-Unterstützung -- Derzeit gibt `_pick_lan_ip` nur IPv4 zurück
- (P3) Unterstützung mehrerer Hailo-Geräte -- Geht von einem festen `hailo-local`-Alias aus. Indexsuffix-Design für Fälle wie mehrere USB-Dongles ist zu berücksichtigen
- (P3) `BackendCatalog.remove_backend()` -- Derzeit aktualisiert `_mark_unreachable` nur den Status und entfernt nicht aus dem Katalog

## Zugehörige Dokumentation

- [LLM Router Setup](./setup.md)
- Design-Spezifikation: `docs/superpowers/specs/2026-04-08-hailo-auto-discovery-design.md`
- Implementierungsplan: `docs/superpowers/plans/2026-04-08-hailo-auto-discovery.md`

## v4.66.2 -- Trusted Peer Auth (Behebung eines echten Authentifizierungslochs bei Geräten)

In v4.66.0's Hailo Auto-Discovery war yu's `/ext/hailo-genai/*`-Erweiterung hinter der Web-Auth-Kette. Wenn der LLM Router-Treiber (der weder ein Bearer-Token noch eine Session hat) versuchte zu proben/zu versenden, gab die Auth-Middleware Honeypot-HTML zurück, verursachte JSON-Parse-Fehler und das Backend blieb als `unreachable` stecken.

### Funktionsweise

- Ein neuer `TrustedPeerRegistry` initialiert `127.0.0.1` / `::1` beim Start
- Wenn `LlmRouterMdnsBridge` einen Peer erfolgreich verifiziert (HTTP GET zu `/api/mdns/identity` + node_id Match-Bestätigung), werden alle angekündigten Adressen dieses Peers zur Registry hinzugefügt
- `auth_chain.check_trusted_peer` umgeht PIN-Authentifizierung beim Empfang einer Anfrage für `/ext/<name>/v1/*`-Pfade, wenn remote_addr in der Registry ist
- Existierende API-Schlüssel / Session / Cookie-Authentifizierungspfade bleiben unverändert

### Beziehung zum Quick Lock

- **loopback** (yu's eigene Self-Probe): Immer erfolgreich, auch während quick_lock
- **peer IP**: Anfragen werden während quick_lock abgelehnt (`check_quick_lock` gibt 503 zurück). Dies bedeutet, dass Peers auch den "Benutzer hat absichtlich gesperrt"-Status respektieren

Dies ermöglicht die folgenden Szenarien wie erwartet zu funktionieren:

- pi2's `hailo-local` Self-Probe (`http://localhost:5000/ext/hailo-genai/v1/models`)
- Cross-Node-Versand von Windows zu pi2's `mdns-<id>-hailo` (`http://192.168.50.4:5000/ext/hailo-genai/v1/chat/completions`)

### Konfiguration

Es sind keine Änderungen der Konfigurationsdatei erforderlich. Auch in Umgebungen, in denen mDNS deaktiviert ist, funktioniert das Loopback-Seed noch, daher ist die Self-Probe-Behebung bedingungslos verfügbar.

### Debugging

Setzen Sie die Umgebungsvariable `TAGDB_DEBUG_TRUSTED_PEERS=1` vor dem Start von yu, um ein `trusted_ips`-Feld zur `/api/mdns/peers`-Antwort hinzuzufügen. Setzen Sie dies nicht in der Produktion (die Vertrauensliste ist im Wesentlichen eine "Angriffsziellist" und sollte nicht auf nicht authentifizierten Endpunkten verfügbar gemacht werden).

### Sicherheitsgrenze

Betrieb unter der "vertrauenswürdiges LAN"-Annahme (gleiche Prämisse wie v4.64.0 mDNS Phase B). Schutz gegen böswillige Knoten mit physischem Zugang zum LAN liegt außerhalb des Umfangs -- verwenden Sie die `/llm-router` WebUI Deaktivierungsschalter oder quick_lock für solche Fälle.

Siehe `docs/superpowers/specs/2026-04-09-trusted-peer-auth-design.md` für Details.
