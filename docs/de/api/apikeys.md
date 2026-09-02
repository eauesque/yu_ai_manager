# API-Schlüssel API

APIs zum Erstellen, Auflisten und Löschen von API-Schlüsseln. Alle Endpunkte erfordern PIN-Sitzungsauthentifizierung.

API-Schlüssel werden im Format `sk_` + 32 Hex-Zeichen (128 Bit) generiert. Nur der Hash wird serverseitig gespeichert; der unverarbeitete Schlüssel wird nur einmal bei der Erstellung zurückgegeben.

## Bereiche

API-Schlüssel können Bereiche zugewiesen werden, um zu beschränken, auf welche Endpunkte sie zugreifen können. Schlüssel ohne Bereiche werden standardmäßig auf schreibgeschützten Zugriff beschränkt.

| Bereich | Beschreibung |
|-------|-------------|
| `read` | Suche, Dateidetails, Miniaturen, Statistiken |
| `rate` | Bewertung abrufen/setzen/Batch |
| `tag.write` | Tag hinzufügen/entfernen |
| `collection.write` | Sammlung erstellen/aktualisieren/löschen, Batch-Add, Favoriten |
| `annotate` | Anmerkung lesen/schreiben/löschen |
| `scan` | Scan starten/abbrechen/fortsetzen |
| `admin` | API-Schlüsselverwaltung, Einstellungen, Sicherung/Wiederherstellung |

## POST /api/apikeys

Erstelle einen neuen API-Schlüssel.

### Ratenumgrenzung

WRITE (Bereich: `admin`)

### Authentifizierung

PIN-Sitzung oder API-Schlüssel mit Bereich `admin`

### Anfrage

```json
{
  "label": "Meine Integration",
  "scopes": ["read", "rate"]
}
```

| Parameter | Typ | Erforderlich | Beschreibung |
|-----------|------|----------|-------------|
| `label` | string | Nein | Identifizierungsetikett für den Schlüssel. Standardmäßig `Key <timestamp>` wenn weggelassen |
| `scopes` | string[] | Nein | Array von Bereichen. Weglassen oder leeres Array für schreibgeschützten Zugriff |

### Antwort (201)

```json
{
  "id": "ak_1a2b3c4d5e6f7890",
  "key": "sk_abcdef1234567890abcdef1234567890",
  "key_prefix": "sk_abcdef12",
  "label": "Meine Integration",
  "created_at": 1709500000,
  "scopes": ["read", "rate"]
}
```

> **Hinweis**: Das Feld `key` ist nur in der Erstellungsantwort enthalten. Dieser Wert kann nicht erneut abgerufen werden, daher speichern Sie ihn an einem sicheren Ort.

### Fehler

| Status | Beschreibung |
|--------|-------------|
| 400 | Ungültiger Bereich angegeben |

## GET /api/apikeys

Alle API-Schlüssel auflisten. Hashes sind nicht enthalten; nur das Präfix wird zurückgegeben.

### Authentifizierung

PIN-Sitzung oder API-Schlüssel mit Bereich `admin`

### Parameter

Keine

### Antwort

```json
{
  "keys": [
    {
      "id": "ak_1a2b3c4d5e6f7890",
      "key_prefix": "sk_abcdef12",
      "label": "Meine Integration",
      "created_at": 1709500000,
      "last_used_at": 1709600000,
      "scopes": ["read", "rate"]
    }
  ]
}
```

| Feld | Typ | Beschreibung |
|-------|------|-------------|
| `id` | string | Schlüssel-ID (Präfix `ak_`) |
| `key_prefix` | string | Erste 10 Zeichen des Schlüssels (zur Identifikation) |
| `label` | string | Benutzerdefiniertes Etikett |
| `created_at` | int | Erstellungszeit (Unix-Zeitstempel) |
| `last_used_at` | int/null | Letzte Nutzungszeit. `null` wenn niemals verwendet |
| `scopes` | string[] | Zugewiesene Bereiche. Feld wird weggelassen, wenn keine Bereiche gesetzt sind |

## DELETE /api/apikeys/<key_id>

Einen API-Schlüssel löschen (widerrufen).

### Ratenumgrenzung

WRITE (Bereich: `admin`)

### Authentifizierung

PIN-Sitzung oder API-Schlüssel mit Bereich `admin`

### Parameter

| Parameter | Typ | Beschreibung |
|-----------|------|-------------|
| `key_id` | string | API-Schlüssel-ID (Pfad-Parameter) |

### Antwort

```json
{
  "deleted": "ak_1a2b3c4d5e6f7890"
}
```

### Fehler

| Status | Beschreibung |
|--------|-------------|
| 404 | Schlüssel mit der angegebenen ID nicht gefunden |

## Verwendung von API-Schlüsseln

Verwenden Sie den erstellten API-Schlüssel über den `Authorization`-Header:

```
Authorization: Bearer sk_abcdef1234567890abcdef1234567890
```

Anfragen, die mit API-Schlüsseln authentifiziert sind, erfordern nicht den CSRF-Header (`X-Requested-With`).
