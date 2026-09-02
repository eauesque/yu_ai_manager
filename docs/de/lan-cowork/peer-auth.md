# PIN-Authentifizierung zwischen Peers / Token-Pairing

**Implementierungsversion**: 4.92.0
**Verwandte Dateien**: `extensions/builtin_lan_cowork/`, `core/lan_cowork_core/`

---

## Übersicht

Vor v4.92 wurde bei der Kommunikation zwischen Peers im LAN die Gegenseite nur über den `X-Peer-Id`-Header identifiziert.
Da jeder im LAN diesen Header fälschen konnte, war die Sicherheit unzureichend.

Ab v4.92 wurde auf ein **PIN-Approval-basiertes Token-Pairing**-Verfahren umgestellt.

- Bei der Erstverbindung wird ein „Pairing-Request" gesendet
- Der Administrator der Gegenseite bestätigt im Verwaltungsbildschirm und gibt eine 6-stellige PIN aus
- Nach Eingabe der PIN wird ein Bearer-Token (30 Tage gültig) ausgestellt
- Danach erfolgt die Authentifizierung über `Authorization: Bearer <token>`

Das alte `X-Peer-Id`-Header-Verfahren kann über Konfiguration aus Kompatibilitätsgründen erhalten bleiben, DELETE-Operationen erfordern jedoch stets die neue Authentifizierung.

---

## Pairing-Ablauf

```
[Verbindungsinitiierender Peer A]          [Zielpeer B]
       |                                      |
       |--- POST /api/lan/pair/request ------->|
       |    (peer_id, display_name, public_key)|
       |                                      |
       |                              Administrator prüft/bestätigt in /lan-cowork/peers
       |                                      |
       |<--- SSE: peer_pairing.pin_ready ------|
       |    (6-stellige PIN, 5 Min. gültig)    |
       |                                      |
       |--- POST /api/lan/pair/verify -------->|
       |    (peer_id, pin)                     |
       |                                      |
       |<--- 200 OK: { token, expires_at } ----|
       |    (Bearer-Token, 30 Tage gültig)     |
       |                                      |
       |--- Ab jetzt Authorization: Bearer <token> |
```

### Details der Schritte

| Schritt | Endpunkt | Beschreibung |
|----------|---------------|------|
| 1. Request senden | `POST /api/lan/pair/request` | Peer-ID, Anzeigename und öffentlicher Schlüssel senden |
| 2. Auf Freigabe warten | — | Administrator prüft in `/lan-cowork/peers` |
| 3. PIN ausstellen | — | Wenn der Administrator auf „Bestätigen" klickt, wird eine 6-stellige PIN erzeugt (5 Min. gültig) |
| 4. PIN verifizieren | `POST /api/lan/pair/verify` | PIN senden und Bearer-Token empfangen |
| 5. Authentifizierte Kommunikation | — | Header `Authorization: Bearer <token>` setzen |

---

## Verwaltungsbildschirm (`/lan-cowork/peers`)

### Ausstehende Requests

Wenn ein Pairing-Request von einem neuen Peer eintrifft, wird er im Tab „Ausstehend" angezeigt.

- **Bestätigen**: Generiert eine PIN und benachrichtigt den anfragenden Peer per SSE
- **Ablehnen**: Löscht den Request. Der anfragende Peer erhält 403

### Liste verbundener Peers

Bereits gepairter Peers werden samt Gültigkeitsdauer ihrer Tokens aufgelistet.

| Spalte | Inhalt |
|----|------|
| Anzeigename | Name des Peers |
| IP-Adresse | Zuletzt bestätigte Quell-IP |
| Ablaufdatum | Ablaufdatum des Bearer-Tokens (30 Tage) |
| Letzte Verbindung | Zeitpunkt des letzten Heartbeats |
| Aktion | Button zum Widerrufen des Tokens |

### Token widerrufen

Ein Klick auf „Widerrufen" invalidiert das Bearer-Token des Peers sofort.
Beim nächsten Kommunikationsversuch gibt der Server 401 zurück, und der Peer versucht automatisch, erneut zu pairen.

---

## Konfigurationselemente

Die Konfiguration kann im Abschnitt `extensions` der `config.json` unter dem Eintrag `builtin-lan-cowork` oder im Tab „LAN-Zusammenarbeit" im Einstellungsbildschirm geändert werden.

### `ip_check_mode`

Legt fest, wie die Quell-IP überprüft wird.

| Wert | Verhalten |
|----|------|
| `strict` | Nur exakte Übereinstimmung mit der IP zum Zeitpunkt der Token-Ausstellung zulassen (Standard) |
| `cidr` | Zulassen, wenn im durch `allowed_cidr` angegebenen Bereich |
| `rfc1918` | Alle privaten IP-Adressen zulassen (192.168.x.x / 10.x.x.x / 172.16-31.x.x) |

### `allow_legacy_auth`

Legt fest, ob die Kompatibilität zur alten `X-Peer-Id`-Header-Authentifizierung erhalten bleibt.

- `true`: Bestimmte Operationen sind auch nur mit `X-Peer-Id`-Header zulässig (Standard: `true`)
- `false`: Verbindungen ohne Bearer-Token werden vollständig abgelehnt

> **Hinweis**: Operationen, die die `DELETE`-Methode verwenden (Scan-Stopp, erzwungenes Löschen usw.), benötigen unabhängig von `allow_legacy_auth` stets ein Bearer-Token.

### `protect_heartbeat`

Legt fest, ob auch der Heartbeat-Endpunkt (`/api/lan/heartbeat`) Authentifizierung erfordert.

- `true`: Auch Heartbeat erfordert Bearer-Token
- `false`: Heartbeat passiert ohne Authentifizierung (Standard: `false`)

Da Heartbeats häufig gesendet werden, verhindert `false` Verzögerungen beim Erkennen abgelaufener Tokens.

### `protect_events`

Legt fest, ob auch der SSE-Eventstream (`/api/events/`) Authentifizierung erfordert.

- `true`: Auch SSE erfordert Bearer-Token
- `false`: SSE passiert ohne Authentifizierung (Standard: `false`)

---

## Sicherheitshinweise

### Token-Hashing

Ausgestellte Bearer-Tokens werden **nicht im Klartext** in der Datenbank gespeichert.
Sie werden mit scrypt (N=16384, r=8, p=1) gehasht gespeichert.
Selbst bei DB-Leak kann das Original-Token nicht wiederhergestellt werden.

### Log-Maskierung

- Der Header `Authorization: Bearer <token>` wird beim Loggen automatisch durch `Bearer [REDACTED]` ersetzt
- PIN-Codes erscheinen ebenfalls nicht im Log

### Rate-Limits

Zur Abwehr von DoS-Angriffen und Brute-Force gelten folgende Rate-Limits.

| Endpunkt | Limit |
|---------------|------|
| `POST /api/lan/pair/request` | 10 pro Minute pro IP |
| `POST /api/lan/pair/verify` | 30 pro Minute pro IP |

Die PIN läuft nach 5 Minuten automatisch ab und kann pro Request nur einmal verifiziert werden.

---

## Fehlerbehebung

### Pairing-Request kommt nicht an

- Prüfen Sie, ob die URL des Ziel-Peers korrekt konfiguriert ist
- Prüfen Sie, ob der Port durch eine Firewall blockiert ist
- Prüfen Sie im Log des Ziel-Peers, ob der `pair/request` empfangen wurde

### PIN ist abgelaufen

Die PIN ist 5 Minuten gültig. Bei Ablauf einfach erneut auf „Bestätigen" im Verwaltungsbildschirm klicken, um eine neue PIN auszustellen.

### Token funktioniert plötzlich nicht mehr

Mögliche Ursachen:

1. Administrator hat das Token im Verwaltungsbildschirm widerrufen
2. 30-tägige Gültigkeit ist abgelaufen
3. Bei `ip_check_mode: strict` hat sich die IP-Adresse geändert

Führen Sie ein erneutes Pairing durch.

### Nach Setzen von `allow_legacy_auth` auf `false` keine Verbindung mehr

Wenn bestehende Peers noch die alte Authentifizierung nutzen, werden alle mit 401 abgewiesen.
Schließen Sie an jedem Peer das erneute Pairing ab, bevor Sie `allow_legacy_auth: false` setzen.
