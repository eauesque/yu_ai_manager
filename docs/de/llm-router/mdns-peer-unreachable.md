# mDNS-Backend bleibt dauerhaft 'nicht erreichbar'

Ursachen, Diagnose und Behebung für den Fall, dass ein per mDNS-Autodiscovery
des LLM-Routers hinzugefügtes Backend im Zustand „nicht erreichbar (unreachable)"
verbleibt und sich nicht erholt.

---

## Strukturübersicht

```
MdnsService (zeroconf layer)
  └─ on_peer_added / on_peer_updated / on_peer_removed
       └─ LlmRouterMdnsBridge
            ├─ _verify()       ← HTTP-Prüfung via /api/mdns/identity
            ├─ _apply_peer_to_catalog()  ← Registrierung im BackendCatalog
            ├─ _enter_cooldown() / _in_cooldown()  ← Wiederholungsbeschränkung nach Fehler
            └─ retry_pending_peers()  ← 60-Sekunden-Sweep (ab v4.91.15)
```

**Wichtiger Ablauf**:

1. zeroconf erkennt einen Peer → `on_peer_added` wird aufgerufen
2. `_verify()` ruft `/api/mdns/identity` auf und prüft `node_id` und `product`
3. Erfolg → `_apply_peer_to_catalog()` fügt das Backend dem Catalog hinzu
4. Fehler → 60-Sekunden-Cooldown; Ereignisse für dieselbe `node_id` werden ignoriert
5. **Ab v4.91.15**: Ein 60-Sekunden-Sweep-Task wiederholt nicht erreichbare Peers nach Ablauf des Cooldowns

---

## Häufige Muster für „nicht erreichbar"

### Muster A — Erster verify schlägt fehl → Stille durch Cooldown

**Symptom**: Backend wird im LLM-Router angezeigt, aber status=unreachable.  
**Ursache**:
- HTTP-Server des Gegensystems war beim Start noch nicht bereit
- Der eigene Port hatte sich geändert und der Peer referenzierte einen alten TXT-Eintrag (Fehler vor v4.91.14 mit `--port`-Override: behoben in 35a3679a)

**Verhalten (vor v4.91.14)**: Nach Ablauf des Cooldowns (60 Sek.) wird auf das nächste `on_peer_updated`-Ereignis gewartet; bleibt dieses aus, erfolgt keine Wiederherstellung.

**Verhalten (ab v4.91.15)**: Nach Cooldown-Ablauf wird beim nächsten Sweep-Tick (max. 60 Sek. später) automatisch erneut versucht → bei Erfolg wird der Catalog aktualisiert.

---

### Muster B — zeroconf löst `ServiceStateChange.Updated` nicht aus

**Symptom**: Peer wurde neu gestartet, LLM-Router zeigt weiterhin den alten Status.  
**Ursache**: Je nach Cache-Zustand von zeroconf kann beim Ändern eines TXT-Eintrags kein `Updated`-Ereignis ausgelöst werden (bekanntes Verhalten der zeroconf-Bibliothek).  
**Behebung**: Der Sweep-Task in v4.91.15 erkennt dies innerhalb von 60 Sekunden.

---

### Muster C — Port des Gegensystems weicht vom beworbenen Wert ab

**Symptom**: curl erreicht den Peer, aber verify läuft kontinuierlich in den Timeout.  
**Ursache**: `--port`-CLI-Flag wird genutzt, aber `server.port` in config.json enthält noch den alten Wert → falscher Port wird in der mDNS-TXT-Meldung beworben.  
**Korrektur**: In v4.91.14 (35a3679a) behebt: `config["server"]["port"]` wird mit dem tatsächlichen Port überschrieben. Falls ein altes Startskript config.json direkt ändert, auch diese Datei prüfen.

---

### Muster D — Nicht in trusted_peer_registry eingetragen

**Symptom**: LLM-Router zeigt „ready", aber Proxying zu `/ext/<name>/v1/*` liefert 403.  
**Ursache**: verify war erfolgreich und der Catalog wurde aktualisiert, aber der Prozess wurde vor dem Aufruf von `_apply_peer_to_catalog()` neu gestartet, oder `service_kind != "yu"` sorgte dafür, dass die Registry-Registrierung übersprungen wurde (Bare-Ollama-Peers werden nicht registriert).  
**Prüfung**:
```bash
curl -s http://127.0.0.1:PORT/api/mdns/peers | python3 -m json.tool | grep -E 'node_id|trusted'
```

---

## Diagnoseschritte

### 1. Aktuellen Peer-Status prüfen

```bash
# Liste bekannter Peers
curl -s http://127.0.0.1:PORT/api/mdns/peers | python3 -m json.tool

# LLM-Router-Backend-Liste (mDNS-Einträge haben Alias-Präfix "mdns-")
curl -s http://127.0.0.1:PORT/api/llm_router/status | python3 -m json.tool
```

### 2. Prüfen, ob der Gegenpeer den eigenen Identity-Endpunkt erreicht

Auf dem Gegenpeer ausführen:
```bash
curl -v http://<eigene-LAN-IP>:<PORT>/api/mdns/identity
```

Erwartete Antwort:
```json
{"product": "yu_ai_manager", "node_id": "...", "version": "..."}
```

Bei Fehler:
- Firewall- oder Routing-Problem
- Port stimmt zwischen tatsächlichem Wert und beworbenem Wert nicht überein (prüfen, ob `--port` verwendet wird)

### 3. Beworbenen Port prüfen

```bash
# Startprotokoll enthält "web_port"
grep -i "web_port\|mdns.*port\|effective_port" logs/app.log | tail -20

# Alternativ über Settings-API
curl -s http://127.0.0.1:PORT/api/server/info | python3 -m json.tool | grep port
```

### 4. Cooldown-Status prüfen

GUI: **LLM-Router** > Backend-Karte > Details zeigt `last_error` und `last_seen_at`.
Bei „identity verification failed" ist der Peer erreichbar, aber Inhalt stimmt nicht überein (node_id / product-Konflikt). Bei „timeout" erreicht HTTP den Peer nicht.

### 5. Sweep-Logs prüfen

```bash
grep "\[mdns\] sweep" logs/app.log
```

`sweep re-verified peer <8Zeichen>` zeigt an, dass der Sweep die Wiederherstellung bewirkt hat.

---

## Manuelle Wiederherstellung

Um nicht auf den nächsten Sweep-Tick warten zu müssen:

### Methode 1: Gegenpeer neu starten

Beim Neustart löst zeroconf `ServiceStateChange.Removed` + `Added` aus →
`on_peer_removed` löscht den Cooldown → `on_peer_added` führt sofort eine neue Prüfung durch.

### Methode 2: mDNS-Dienst über die Einstellungs-UI neu starten

**Einstellungen** > **LLM-Router** > Schaltfläche **mDNS neu starten** (falls vorhanden).

### Methode 3: Anwendung neu starten

Der Cooldown existiert nur im Arbeitsspeicher. Ein Neustart setzt alle Cooldowns zurück
und prüft alle Peers unmittelbar nach dem Start erneut.

---

## Prävention

| Prüfpunkt | Methode |
|---|---|
| Bei Nutzung von `--port`: stimmt `server.port` in config.json überein? | config.json prüfen |
| Ist eingehender Traffic auf `PORT` durch die Firewall erlaubt? | `sudo ufw status` / macOS-Einstellungen |
| Wird in Umgebungen mit mehreren NICs an die richtige LAN-Schnittstelle gebunden? | `mdns.bind_address` in config.json |
| Wird v4.91.15 oder höher genutzt (mit Sweep-Task)? | `curl .../api/server/info` |

---

## Zugehörige Dateien

| Datei | Funktion |
|---|---|
| `core/llm_router/mdns_integration.py` | `LlmRouterMdnsBridge`, Cooldown, retry_pending_peers |
| `core/web/runtime_mdns.py` | Sweep-Task starten/stoppen |
| `core/mdns/service.py` | zeroconf-Wrapper, `list_peers()` |
| `core/web/trusted_peer_registry.py` | Cross-Node-Authentifizierung für `/ext/*` |
