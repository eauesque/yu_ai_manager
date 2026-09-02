# Videoanalyse API

APIs zur Verwaltung der Videoanalyse-Konfiguration und Statusüberprüfung. Steuert die Einstellungen zum Extrahieren von Keyframes aus Videodateien.

## GET /api/video-analysis/config

Rufen Sie die aktuelle Videoanalyse-Konfiguration ab. Gibt gespeicherte Einstellungen zusammengeführt mit Standardwerten zurück.

### Parameter

Keine

### Antwort

```json
{
  "config": {
    "enabled": true,
    "keyframe_count": 4,
    "strategy": "uniform",
    "scene_threshold": 0.4,
    "store_per_keyframe": false
  }
}
```

| Feld | Typ | Standard | Beschreibung |
|-------|------|---------|-------------|
| `enabled` | boolean | `true` | Ob Videoanalyse aktiviert ist |
| `keyframe_count` | int | `4` | Anzahl der zu extrahierenden Keyframes (1-16) |
| `strategy` | string | `"uniform"` | Keyframe-Extraktions-Strategie. `uniform` (gleichmäßig verteilt), `scene` (Scene-Change-Erkennung), `single` (einzelner Frame nur) |
| `scene_threshold` | float | `0.4` | Scene-Change-Erkennungs-Schwelle (0.0-1.0). Wird verwendet, wenn `strategy` `scene` ist |
| `store_per_keyframe` | boolean | `false` | Ob jeder Keyframe einzeln gespeichert wird |

## POST /api/video-analysis/config

Speichern Sie die Videoanalyse-Konfiguration. Nur angegebene Felder werden aktualisiert; weggelassene Felder behalten ihre bestehenden Werte bei.

### Ratenumgrenzung

WRITE

### Anfrage

```json
{
  "enabled": true,
  "keyframe_count": 8,
  "strategy": "scene",
  "scene_threshold": 0.3,
  "store_per_keyframe": false
}
```

Alle Felder sind optional. Nur angegebene Felder werden aktualisiert.

| Parameter | Typ | Erforderlich | Einschränkungen | Beschreibung |
|-----------|------|----------|-------------|-------------|
| `enabled` | boolean | Nein | - | Ob Videoanalyse aktiviert ist |
| `keyframe_count` | int | Nein | 1-16 | Anzahl der zu extrahierenden Keyframes |
| `strategy` | string | Nein | `uniform`, `scene`, oder `single` | Keyframe-Extraktions-Strategie |
| `scene_threshold` | float | Nein | 0.0-1.0 | Scene-Change-Erkennungs-Schwelle |
| `store_per_keyframe` | boolean | Nein | - | Ob jeder Keyframe einzeln gespeichert wird |

### Antwort

Gibt die zusammengeführte Konfiguration nach dem Speichern zurück (gleiches Format wie GET).

```json
{
  "config": {
    "enabled": true,
    "keyframe_count": 8,
    "strategy": "scene",
    "scene_threshold": 0.3,
    "store_per_keyframe": false
  }
}
```

### Fehler

| Status | Code | Bedingung |
|--------|------|-----------|
| 400 | `invalid_json` | Anfragekörper ist nicht ein JSON-Objekt |
| 400 | `invalid_value` | Validierungsfehler (falscher Typ, out-of-range Wert, ungültige Strategie, usw.) |

## GET /api/video-analysis/status

Rufen Sie Videoanalyse-Statusinformationen ab. Gibt ffmpeg-Verfügbarkeit, Videodatei-Anzahl und Anzahl der Dateien mit extrahierten Keyframes zurück.

### Parameter

Keine

### Antwort

```json
{
  "ffmpeg": true,
  "video_files": 150,
  "files_with_keyframes": 42
}
```

| Feld | Typ | Beschreibung |
|-------|------|-------------|
| `ffmpeg` | boolean | Ob ffmpeg auf dem System verfügbar ist |
| `video_files` | int | Gesamtanzahl der Videodateien in der Datenbank (ohne soft-deleted). Unterstützte Erweiterungen: `.mp4`, `.webm`, `.avi`, `.mov`, `.mkv`, `.m4v`, `.ogv` |
| `files_with_keyframes` | int | Anzahl der Dateien mit extrahierten Keyframes |
