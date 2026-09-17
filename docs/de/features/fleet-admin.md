# Fleet-Verwaltung (Fleet Admin)

Die Fleet-Admin-Funktion von LAN Cowork ermöglicht die zentrale Verwaltung mehrerer yu-ai-manager-Knoten im Netzwerk.

## Überblick

- **Maschineninfo-Erfassung**: CPU/RAM/GPU/Datenträger/Version/Betriebszeit jedes Knotens zentral aggregieren
- **Remote-Log-Ansicht**: Logs beliebiger Peers über die UI des zentralen Knotens per SSE live streamen
- **Versions-Update-Verteilung**: Zentralen `git pull --ff-only` + Graceful Restart an bestimmte Peers anweisen

## Voraussetzungen

- LAN Cowork-Erweiterung aktiviert (`extensions["builtin-lan-cowork"].enabled = true`)
- Pairing zwischen Peers abgeschlossen
- Als Git-Repository geclont (bei Verwendung der Update-Funktion)
- `psutil>=5.9` in der Python-Virtualumgebung installiert

## Setup

### Chief-Knoten-Konfiguration

In `config.json` hinzufügen:

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "fleet": {
        "chief": true,
        "allow_remote_update": true,
        "allow_update_from": [
          "<Gepaarte peer_id>"
        ],
        "allow_log_stream_from": [
          "<Gepaarte peer_id>"
        ],
        "allowed_branches": [
          "main"
        ],
        "timings": {
          "chief_observation_sec": 25,
          "peers_poll_interval_sec": 30,
          "heartbeat_timeout_sec": 60,
          "update_job_timeout_sec": 600,
          "postcheck_timeout_sec": 180
        }
      }
    }
  }
}
```

### Reguläre Knoten-Konfiguration

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "fleet": {
        "chief": false,
        "allow_remote_update": true,
        "allow_update_from": [
          "<Chief peer_id>"
        ],
        "allow_log_stream_from": [
          "<Chief peer_id>"
        ],
        "allowed_branches": [
          "main"
        ]
      }
    }
  }
}
```

## Zugriff auf die Fleet-Verwaltungs-UI

Im Browser des Chief-Knotens auf `/ext/lan_cowork/fleet/ui` zugreifen.

Auf regulären Knoten gibt diese URL einen 404-Fehler.

## Tab-Funktionen

### Übersichts-Tab

- Kartenanzeige aller Knoten (mit CPU/RAM/GPU/Datenträger-Auslastungsbalken)
- Statusanzeige: Online / Offline / Informationsabruf fehlgeschlagen
- `[CHIEF]`-Badge für den Chief-Knoten
- Automatische Aktualisierung alle 30 Sekunden + manueller Aktualisierungsknopf
- Warnbanner bei Erkennung mehrerer Chiefs

### Log-Tab

- Live-Anzeige von Logs beliebiger Peers per SSE (wie tail -f)
- Level-Filter (DEBUG / INFO / WARNING / ERROR)
- Suchfeld (client-seitiger Filter)
- Auto-Scroll EIN/AUS
- Pause / Fortsetzen

### Update-Tab

- Vergleichstabelle für Version / Git-Commit / Branch
- "Pull & Restart"-Schaltfläche für einzelne Knoten
- Massen-Update mehrerer Knoten (Dispatch)
- Fortschrittsanzeige (precheck → fetching → pulling → restarting → online)
- Chief selbst wird von Massen-Updates ausgeschlossen (nur Einzelschaltfläche)

## Sicherheit

### Zweischichtige Autorisierung

1. **Pairing (Identitätsprüfung)**: Bearer-Token zur Identifikation der Person
2. **Allowlist (Berechtigungen)**: Explizite Erlaubnis pro Operation

Gepaart sein bedeutet nicht automatisch alle Berechtigungen.

### Allowlist-Konfigurationsbeispiel

```json
"allow_update_from": [
  "abc123def456",
  {"peer_id": "def456abc789"}
]
```

- String- und `{peer_id: ...}`-Format werden beide unterstützt
- Die eigene peer_id wird automatisch hinzugefügt (keine Konfiguration erforderlich)

## Automatische Chief-Degradierung

Wenn mehrere Knoten mit `chief = true` im selben Netzwerk gestartet werden, wird der zuletzt gestartete Knoten automatisch degradiert (nach `chief_observation_sec` Sekunden Beobachtung).

Nach einer Degradierung ist ein Neustart nach Konfigurationsänderung erforderlich, um wieder Chief zu werden (keine automatische Beförderung).

## Git-Update-Einschränkungen

- Es wird nur `git pull --ff-only` verwendet (kein merge/rebase)
- Bei nicht möglichem Fast-Forward wird sofort `failed` zurückgegeben (kein Ändern des Working Tree)
- Bei schmutzigem Working Tree wird das Update abgelehnt

## Fehlerbehebung

| Symptom | Ursache | Lösung |
|---|---|---|
| `/fleet/ui` gibt 404 | `chief = true` nicht gesetzt | config.json prüfen und neu starten |
| `/fleet/info` gibt 500 | psutil nicht installiert | `uv pip install psutil>=5.9` |
| `git_not_available`-Fehler | git nicht vorhanden oder PATH falsch | Git-Installation prüfen |
| `postcheck_online`-Timeout nach Update | Neustart dauerte mehr als 3 Minuten | `postcheck_timeout_sec` verlängern |
| Mehrfach-Chief-Warnbanner verschwindet nicht | Alter Chief-Prozess läuft noch | Alten Chief neu starten |

## API-Referenz

### Alle Knoten

| Endpunkt | Beschreibung |
|---|---|
| `GET /ext/lan_cowork/fleet/info` | Maschineninfo (Bearer-Auth erforderlich) |
| `GET /ext/lan_cowork/fleet/logs/stream` | Eigenem Log-SSE (Allowlist-Autorisierung) |
| `POST /ext/lan_cowork/fleet/update` | git pull + Neustart (Allowlist-Autorisierung) |
| `GET /ext/lan_cowork/fleet/update/status` | Update-Job-Status abfragen |

### Nur Chief-Knoten

| Endpunkt | Beschreibung |
|---|---|
| `GET /ext/lan_cowork/fleet/peers` | Aggregierte Info aller Peers |
| `GET /ext/lan_cowork/fleet/logs/stream?peer_id=X` | Log-SSE-Relay für bestimmten Peer |
| `POST /ext/lan_cowork/fleet/update/dispatch` | Massen-Update an mehrere Peers |
| `GET /ext/lan_cowork/fleet/update/dispatch/status` | Dispatch-Fortschritt abfragen |
| `GET /ext/lan_cowork/fleet/ui` | Fleet-Verwaltungs-UI |
