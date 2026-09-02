# UI-Verwaltungs API

APIs zum Auflisten, Wechseln, Installieren und Deinstallieren von UI-Designs.

## GET /api/ui/list

Alle installierten UIs auflisten. Gibt Manifest-Informationen, aktiven Status und ob Template-/Static-Dateien für jede UI vorhanden sind.

### Parameter

Keine

### Antwort

```json
{
  "data": {
    "uis": [
      {
        "name": "default",
        "active": true,
        "manifest": {
          "name": "Default UI",
          "version": "1.0.0",
          "description": "Built-in reference UI"
        },
        "has_templates": true,
        "has_static": true
      },
      {
        "name": "custom-dark",
        "active": false,
        "manifest": {
          "name": "Custom Dark",
          "version": "0.2.0",
          "description": "Dark theme variant"
        },
        "has_templates": true,
        "has_static": true
      }
    ]
  }
}
```

| Feld | Typ | Beschreibung |
|-------|------|-------------|
| `name` | string | UI-Verzeichnisname |
| `active` | boolean | Ob dies die derzeit aktive UI ist |
| `manifest` | object | Inhalt von `manifest.json` |
| `has_templates` | boolean | Ob ein `templates/`-Verzeichnis vorhanden ist |
| `has_static` | boolean | Ob ein `static/`-Verzeichnis vorhanden ist |

## POST /api/ui/switch

Wechseln Sie die aktive UI. Die Änderung wird in `config.json` gespeichert und erfordert einen Server-Neustart, um wirksam zu werden.

### Ratenumgrenzung

WRITE

### Anfrage

```json
{
  "name": "custom-dark"
}
```

| Parameter | Typ | Erforderlich | Beschreibung |
|-----------|------|----------|-------------|
| `name` | string | Ja | Ziel-UI-Name. Nur alphanumerische Zeichen, Bindestriche und Unterstriche sind zulässig |

### Antwort

```json
{
  "name": "custom-dark",
  "restart_required": true
}
```

### Fehler

| Status | Bedingung |
|--------|-----------|
| 400 | UI-Name ist leer oder enthält ungültige Zeichen |
| 404 | Angegebene UI existiert nicht |
| 400 | `manifest.json` fehlt oder ist ungültig |
| 500 | Speichern von `config.json` ist fehlgeschlagen |

## POST /api/ui/install

Installieren Sie eine UI von einer URL. **Nur vom Localhost erlaubt.**

### Ratenumgrenzung

WRITE

### Authentifizierung

Erfordert PIN- oder API-Schlüssel-Authentifizierung sowie die Anfrage muss vom Localhost stammen. Remote-Anfragen werden mit 403 abgelehnt.

### Anfrage

```json
{
  "url": "https://github.com/user/my-ui/archive/refs/heads/main.zip"
}
```

| Parameter | Typ | Erforderlich | Beschreibung |
|-----------|------|----------|-------------|
| `url` | string | Ja | URL des UI-Pakets (zip-Archiv, usw.) |

### Antwort

```json
{
  "name": "my-ui",
  "installed": true
}
```

### Fehler

| Status | Bedingung |
|--------|-----------|
| 400 | URL ist leer |
| 403 | Anfrage stammt nicht vom Localhost |

## DELETE /api/ui/<name>/uninstall

Deinstallieren Sie eine UI. **Nur vom Localhost erlaubt.** Die Standard-UI (`default`) kann nicht entfernt werden.

Wenn die deinstallierte UI derzeit aktiv ist, wird die UI-Einstellung in `config.json` zurückgesetzt und die Standard-UI wird wiederhergestellt.

### Ratenumgrenzung

WRITE

### Authentifizierung

Erfordert PIN- oder API-Schlüssel-Authentifizierung sowie die Anfrage muss vom Localhost stammen. Remote-Anfragen werden mit 403 abgelehnt.

### Parameter

| Parameter | Typ | Beschreibung |
|-----------|------|-------------|
| `name` | string | UI-Name (Pfad-Parameter). Nur alphanumerische Zeichen, Bindestriche und Unterstriche |

### Antwort

```json
{
  "name": "custom-dark",
  "uninstalled": true
}
```

### Fehler

| Status | Bedingung |
|--------|-----------|
| 400 | Ungültiger UI-Name oder Versuch, `default` zu deinstallieren |
| 403 | Anfrage stammt nicht vom Localhost |
| 404 | Angegebene UI existiert nicht |
