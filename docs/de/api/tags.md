# Tags API

APIs für Batch-Tag-Operationen und Tag-Vorschlag/Autovervollständigung.

## POST /api/tags/batch-set

Tags in einer Anfrage von mehreren Dateien hinzufügen oder entfernen.

### Ratenumgrenzung

WRITE (~120 req/min, burst 30)

### Anfragekörper

| Feld | Typ | Erforderlich | Beschreibung |
|-------|------|----------|-------------|
| `items` | array | Ja | Liste von Operationen (max 500 Artikel) |
| `items[].file_id` | int | Ja | Datei-ID (positive ganze Zahl) |
| `items[].add` | string[] | Nein | Tag-Namen zum Hinzufügen |
| `items[].remove` | string[] | Nein | Tag-Namen zum Entfernen |

- Jeder Artikel erfordert mindestens einen von `add` oder `remove`
- Tags, die nicht vorhanden sind, werden automatisch erstellt (namespace=null)
- Tags, die über API hinzugefügt werden, haben ihre Quelle auf `"user"` gesetzt
- Verwaiste Tags (keine verbleibenden Datei-Zuordnungen) werden automatisch gelöscht

### Anfrage-Beispiel

```json
{
  "items": [
    {
      "file_id": 42,
      "add": ["landscape", "sunset"],
      "remove": ["lowres"]
    }
  ]
}
```

### Antwort

```json
{
  "total": 1,
  "succeeded": 1,
  "failed": 0,
  "errors": []
}
```

| Feld | Typ | Beschreibung |
|-------|------|-------------|
| `total` | int | Gesamtzahl der verarbeiteten Artikel |
| `succeeded` | int | Anzahl der erfolgreichen Operationen |
| `failed` | int | Anzahl der fehlgeschlagenen Operationen |
| `errors` | array | Liste der Fehlerdetails |

### Fehler

| Status | Beschreibung |
|--------|-------------|
| 400 | Ungültiger Anfragekörper (leere Artikel, ungültige file_id, beide add/remove fehlen, usw.) |
| 429 | Ratenumgrenzung überschritten |

---

## GET /api/tags/suggest

Gibt Tag-Kandidaten zurück, die eine Teilteilzeichenfolge abgleichen. Beabsichtigt für Autovervollständigung.

### Parameter

| Parameter | Typ | Erforderlich | Beschreibung |
|-----------|------|----------|-------------|
| `q` | string | Ja | Suchzeichenfolge |
| `limit` | int | Nein | Maximale Anzahl von Ergebnissen (Standard: 20, max: 100) |

- Suche ist Groß-/Kleinschreibung-unabhängig (LIKE %q%)
- Ergebnisse werden nach `file_count` in absteigender Reihenfolge sortiert
- Ein leeres `q` gibt ein leeres Array zurück

### Antwort

```json
{
  "data": [
    { "id": 1, "tag": "landscape", "namespace": null, "file_count": 150 },
    { "id": 2, "tag": "1girl", "namespace": null, "file_count": 3420 }
  ]
}
```

| Feld | Typ | Beschreibung |
|-------|------|-------------|
| `data[].id` | int | Tag-ID |
| `data[].tag` | string | Tag-Name |
| `data[].namespace` | string\|null | Namespace (normalerweise null) |
| `data[].file_count` | int | Anzahl der mit diesem Tag verknüpften Dateien |
