# Netzwerkverhalten von LAN Cowork (Was auf Ihrem LAN geschieht)

> Zielbereich: v4.538.0 und später Rust standalone (`yu-server`). Für Konfigurationen mit gleichzeitigem
> Python-Backend (hybrid) siehe „Unterschiede zur Python-Version" am Ende dieser Seite.

Diese Seite fasst zusammen: **„Was Ihr Gerät im Netzwerk beginnt zu tun, wenn Sie LAN Cowork aktivieren"**.
Bitte lesen Sie dies, bevor Sie Einstellungen ändern.

---

## Wichtigste Punkte

- **Standardmäßig tut es nichts.** Rust standalone führt keine Überwachung oder Ankündigungen im LAN
  durch, sofern dies nicht durch die nachstehend beschriebenen Einstellungen explizit aktiviert wird.
- Bei Aktivierung werden **Sie von anderen Knoten im gleichen LAN erkannt**. Dies ist beabsichtigtes Verhalten.
- **Die Anwesenheit oder Abwesenheit einer PIN stoppt die Discovery-Ankündigung nicht.** Weitere Details
  finden Sie unter „Beziehung zur PIN (häufiger Missverständnis)".

---

## Was bei Aktivierung startet

| Verhalten | Details |
|---|---|
| **UDP-Abhören** | Bindet an `0.0.0.0:19850` (alle Schnittstellen) |
| **Regelmäßige Ankündigung** | Sendet alle 10 Sekunden ein signiertes HELLO als Broadcast an `255.255.255.255:19850`. Die Nachricht enthält Knoten-ID, öffentlichen Schlüssel, API-Port, Hostname und andere Informationen |
| **Registrierung anderer Knoten** | Validiert die Signatur empfangener HELLOs und speichert Peer-Knoten in der eigenen Peer-Liste (TOFU) |
| **Annahme von inbound HTTP** | Die unten aufgelisteten Peer-Endpunkte beginnen, Antworten zu geben |
| **Lokale Übertragung** | Akzeptierte Peer-Ereignisse werden an die angemeldeten Bildschirme über SSE (`/api/events/stream`) übertragen |
| **Ablauf-Bereinigung** | Bereinigt alle 60 Sekunden abgelaufene Pairing-Anfragen und Klartext-PINs aus dem Speicher |

### Inbound-Endpunkte

| Endpunkt | Authentifizierung |
|---|---|
| `GET /ext/lan_cowork/api/peer/discover` | **Keine Anmeldungssitzung erforderlich** (Abfrage der Peer-Liste) |
| `GET /ext/lan_cowork/api/peer/status` | **Keine Anmeldungssitzung erforderlich** (Deskriptor des eigenen Knotens) |
| `POST /ext/lan_cowork/api/peer/register` | **Keine Anmeldungssitzung erforderlich** (Selbstregistrierung des Peers, wird serverseitig validiert) |
| `POST /ext/lan_cowork/api/peer/pair/request` / `pair/verify` | **Keine Anmeldungssitzung erforderlich** (Pairing initiieren. Ein nicht gepaarter Partner kann keine Sitzung haben) |
| `POST /ext/lan_cowork/api/peer/token/renew` | Signatur + nonce (Bearer nicht erforderlich) |
| `POST /ext/lan_cowork/api/peer/event` / `heartbeat` | Signatur + Bearer-Token |

„Keine Anmeldungssitzung erforderlich" bedeutet **nicht**, dass **keine Authentifizierung vorhanden ist**,
sondern dass **keine Anmeldungssitzung erforderlich ist**. Da ein nicht gepaarter Partner keine Sitzung haben
kann, sind nur diese 5 Pfade ausnahmsweise offen. Alle anderen Pfade erfordern wie gewohnt Anmeldung.

---

## Aktivierung und Deaktivierung

Umschalten über den Abschnitt **`extensions` in `config.json`**.

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "enabled": true
    }
  }
}
```

- **Wenn der Schlüssel fehlt, ist dies „deaktiviert"** (Rust standalone).
- Die Änderung erfordert einen **Neustart**.
- Um vorübergehend zu wechseln, können Sie auch Startup-Optionen verwenden. Die Prioritätsreihenfolge ist
  **Kommandozeile > `config.json` > Umgebungsvariable > Standard**.

| Methode | Aktivierung | Deaktivierung |
|---|---|---|
| Kommandozeile | `--native-daemon` | `--no-native-daemon` |
| Umgebungsvariable | `YU_LAN_COWORK_NATIVE_DAEMON=1` | `=0` |

> Umgebungsvariablen werden nur als „aktiviert" interpretiert, wenn sie `1`, `true` oder `yes` sind. `on`
> oder `Y` werden als **deaktiviert** behandelt.

### Überprüfung der Aktivierung

```bash
curl -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5000/ext/lan_cowork/api/peer/status
```

| Antwort | Bedeutung |
|---|---|
| `200` | Aktiviert. Die Peer-Funktionalität ist aktiv |
| `405` | **Deaktiviert** (Funktion überhaupt nicht eingebaut) |
| `503` | Aktiviert, aber nicht bereit (knoteneigene Schlüssel nicht generiert, oder interne Initialisierung fehlgeschlagen) |

> **Die Anzeige der Erweiterungsliste im UI ist nicht zuverlässig.** In der Liste der Erweiterungen kann
> LAN Cowork als „aktiviert" angezeigt werden, aber dies basiert auf mitgelieferten Informationen und ist
> **nicht gleichbedeutend damit, ob der oben genannte Daemon tatsächlich läuft**. Überprüfen Sie anhand der
> oben stehenden Endpunkt-Antwort oder der Startprotokollzeile `native_daemon=...`.

---

## Beziehung zur PIN (häufiger Missverständnis)

**Es ist nicht richtig, zu denken, dass das LAN nichts berühren kann, wenn keine PIN gesetzt ist.**

- **Korrekt**: Um `--lan` (Abhören auf allen Schnittstellen) zu verwenden, ist eine PIN erforderlich. Ohne
  PIN wird der Start abgebrochen. Das Standardabhören läuft auf `127.0.0.1`, daher ist **bei normalem Start
  die HTTP-Seite vom LAN aus nicht erreichbar**.
- **Hinweis 1**: Wenn Sie `--host` direkt auf eine LAN-IP setzen, wird diese PIN-Erforderlichkeit nicht
  überprüft. Da darüber hinaus ohne PIN sogar das Anmeldungs-Gate offen ist, **vermeiden Sie, das LAN
  ohne PIN freizugeben**.
- **Hinweis 2**: **Die UDP-Ankündigung läuft unabhängig davon, ob eine PIN gesetzt ist.** Wenn aktiviert,
  kündigt auch ein Knoten ohne PIN seine Existenz alle 10 Sekunden im LAN an. Eine PIN beschränkt nur die HTTP-Offenlegung.

Zusammengefasst: **Die PIN reduziert die HTTP-Offenlegung, stoppt aber nicht die Discovery-Ankündigung.**

### Bei Abhören nur auf Loopback (ab v4.539.0)

Wenn die Abhöradresse nur Loopback ist (standardmäßig `127.0.0.1`, was auch auf die Desktop-Version zutrifft),
**kündigt sich dieser Knoten nicht im LAN an**. Andere Knoten könnten sich auch bei einer Ankündigung nicht verbinden.
Nach dem Start wird einmal die folgende Warnung protokolliert (sie ist WARN statt INFO und daher standardmäßig sichtbar).

```
LAN Cowork discovery inactive: server listens on loopback only; bind a LAN address or use --lan
```

Für die Nutzung im LAN binden Sie eine LAN-Adresse oder verwenden Sie `--lan` (`--lan` erfordert eine PIN).

> Vor v4.539.0 kündigte ein nur auf Loopback lauschender Knoten eine LAN-IP an. Peers konnten ihn entdecken,
> aber keine Verbindung herstellen; deshalb wurde dieses Verhalten geändert.

---

## Vor der Aktivierung zu wissen

- **Auch wenn Sie die Funktion deaktivieren, werden die während der Aktivierung aufgezeichneten Peer-Informationen
  nicht automatisch gelöscht.** Darüber hinaus wird **beim ersten Start nach Aktivierung** eine Bereinigung
  alter Peer-Einträge durchgeführt (Einträge, die länger als 7 Tage nicht erreichbar waren, und nicht gepaarte
  Einträge, die länger als 1 Stunde alt sind, werden gelöscht). Es wird empfohlen, vor dem Umschalten ein
  Backup von `tags.db` zu erstellen.
- Empfangene Peer-Ereignisse werden an die SSE übertragen, die angemeldete Bildschirme abonnieren. **Der Inhalt
  stammt von der Remote-Seite** (die Sender-ID wird serverseitig durch den authentifizierten Wert ersetzt).
- Im Protokoll werden **nur die Anzahl, der Typ und die Sender-ID** aufgezeichnet; der Ereignisinhalt wird nicht
  protokolliert.
- Um den Betriebsstatus zu überprüfen, aktivieren Sie INFO auf Protokollstufe (z. B. `RUST_LOG=yu_server=info`).
  Mit Standardeinstellungen werden Zeilen, die Peer-Ereignisempfang anzeigen, nicht ausgegeben.

---

## Unterschiede zur Python-Version

| | Python-Backend hybride Konfiguration | Rust standalone |
|---|---|---|
| Standard | **Aktiviert** (wenn kein Eintrag in `config.json` vorhanden) | **Deaktiviert** (explizite Aktivierung erforderlich) |
| Implementierung | Python-Erweiterung | `yu-server` |

**Rust standalone ist absichtlich auf „standardmäßig deaktiviert" gesetzt.** Dies vermeidet, dass sich das
Netzwerkverhalten durch ein Update ändert. Das Verhalten der Hybrid-Konfiguration hat sich nicht geändert.

> In früherer Dokumentation wurde die Aktivierungseinstellung als `{"lan_cowork": {"enabled": true}}` (auf
> oberster Ebene) angezeigt, aber **dieser Schlüsselpfad wird von keiner Implementierung gelesen.** Der oben
> genannte Abschnitt `extensions` ist der korrekte Speicherort.
