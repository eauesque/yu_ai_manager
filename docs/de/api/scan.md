# Scan API

APIs für Dateisc und Scan-Root-Verwaltung.

## Scan-Steuerung

### POST /api/scan/start

Einen Scan starten.

### Anfrage

```json
{
  "root_indices": [0, 1],
  "force": false
}
```

| Feld | Typ | Beschreibung |
|-------|------|-------------|
| `root_indices` | int[] | Indizes der Roots zum Scannen (weglassen für alle Roots) |
| `force` | bool | Vorhandene Dateien erneut scannen |

### Antwort

```json
{
  "ok": true,
  "message": "Scan gestartet"
}
```

### GET /api/scan/status

Scan-Fortschritt abrufen.

### Antwort

```json
{
  "scanning": true,
  "progress": 45,
  "total": 1500,
  "current_file": "/images/output/00042.png",
  "errors": 0,
  "started_at": 1709500000
}
```

### POST /api/scan/cancel

Einen laufenden Scan abbrechen.

### GET /api/scan/interrupted

Informationen über einen unterbrochenen Scan abrufen.

### POST /api/scan/resume

Einen unterbrochenen Scan fortsetzen.

### POST /api/scan/dismiss

Den Zustand des unterbrochenen Scans verwerfen.

## Scan Worker CLI

Seit v3.27.0 werden Scans in einem separaten Prozess (Worker) ausgeführt.
Der Worker kann zusätzlich zur WebUI API direkt über die CLI gesteuert werden.

```bash
# Einen Scan starten
python -m core.scan.scan_worker start --db ./tags.db --root /path/to/images [--scan-zips] [--force] [--resume]

# Einen Scan stoppen (SIGTERM -> Graceful Shutdown)
python -m core.scan.scan_worker stop

# Status prüfen
python -m core.scan.scan_worker status
```

### IPC-Dateien

| Datei | Inhalt |
|------|---------|
| `/tmp/yu-scan/worker.pid` | Worker PID |
| `/tmp/yu-scan/progress.json` | Fortschritt (JSON: running, phase, current, total, percent, message, detail, error) |

Die WebUI fragt diese Fortschrittsdatei ab und leitet die Daten über `GET /api/scan/status` und SSE-Ereignisse (`scan.progress`, `scan.complete`) weiter.

## Scan-Fehler

### GET /api/scan-errors

Liste der Fehler, die während des Scans aufgetreten sind.

| Parameter | Typ | Beschreibung |
|-----------|------|-------------|
| `type` | string | Fehlertyp-Filter |
| `resolved` | bool | Nur behobene Fehler |
| `limit` | int | Anzahl der Ergebnisse |

### POST /api/scan-errors/<id>/resolve

Markieren Sie einen Fehler als behoben.

### POST /api/scan-errors/clear

Alle behobenen Fehler auf einmal löschen.

## Scan-Root-Verwaltung

### GET /api/scan-roots

Registrierte Scan-Roots auflisten.

### Antwort

```json
{
  "roots": [
    {
      "path": "O:\\webui\\outputs",
      "enabled": true,
      "file_count": 15000
    }
  ]
}
```

### POST /api/scan-roots

Einen Scan-Root hinzufügen.

```json
{
  "path": "O:\\webui\\outputs"
}
```

### PUT /api/scan-roots/<index>

Einen Scan-Root aktualisieren (Pfad ändern, aktiviert/deaktiviert umschalten).

### DELETE /api/scan-roots/<index>

Einen Scan-Root löschen.

## Hash-Backfill

### POST /api/hash-backfill/start

Starten Sie die Hintergrund-Hash-Berechnung für vorhandene Dateien.

### GET /api/hash-backfill/status

Fortschritt abrufen.

### POST /api/hash-backfill/cancel

Abbrechen Sie die Berechnung.

## Hintergrund-Jobs

### GET /api/jobs/status

Status aller Hintergrund-Jobs. Verwendet für UI-Banner-Anzeige.

```json
{
  "jobs": [
    {
      "type": "scan",
      "status": "running",
      "progress": 45,
      "total": 1500
    }
  ]
}
```
