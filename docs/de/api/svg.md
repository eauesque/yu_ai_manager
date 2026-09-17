# SVG-Rasterisierungs API

API zum Konvertieren von SVG-Vektorgrafiken zu PNG/WebP-Bitmaps.
Entworfen für die Integration in die img2img-Pipeline — die zurückgegebenen Base64-Bilddaten können direkt an NovelAI Bridge oder SD WebUI Bridge übergeben werden.

## GET /api/svg/info

Überprüfen Sie die Verfügbarkeit der SVG-Rasterisierung.

- **Ratenumgrenzung**: Keine (GET)

### Antwort

```json
{
  "available": true,
  "backend": "resvg"
}
```

| Feld | Typ | Beschreibung |
|-------|------|-------------|
| `available` | bool | Ob Rasterisierung verfügbar ist |
| `backend` | string \| null | Aktives Backend (`"resvg"` oder `null`) |

---

## POST /api/svg/rasterize

Rasterisieren Sie ein SVG zu einer PNG/WebP-Bitmap.

- **Ratenumgrenzung**: HEAVY

### Anfragekörper

| Parameter | Typ | Erforderlich | Beschreibung |
|-----------|------|----------|-------------|
| `file_id` | int | *1 | SVG-Datei-ID aus der Datenbank |
| `svg_path` | string | *1 | Absoluter Pfad zu einer SVG-Datei |
| `svg_data` | string | *1 | Inline SVG-XML-String |
| `width` | int | Nein | Ausgabebreite (Standard: 1024) |
| `height` | int | Nein | Ausgabehöhe (Standard: 1024) |
| `format` | string | Nein | `"png"` oder `"webp"` (Standard: `"png"`) |
| `background` | string | Nein | Hintergrundfarbe (z.B. `"#ffffff"`). Transparent wenn weggelassen |

> *1: Geben Sie genau eine von `file_id`, `svg_path` oder `svg_data` an.

### Anfrage-Beispiel

```json
{
  "file_id": 123,
  "width": 832,
  "height": 1216,
  "format": "png",
  "background": "#ffffff"
}
```

### Antwort

```json
{
  "ok": true,
  "base64": "iVBORw0KGgo...",
  "width": 832,
  "height": 1216,
  "format": "png",
  "size_bytes": 45678
}
```

| Feld | Typ | Beschreibung |
|-------|------|-------------|
| `ok` | bool | Erfolgs-Flag |
| `base64` | string | Base64-codierte PNG/WebP-Daten |
| `width` | int | Aktuelle Ausgabebreite |
| `height` | int | Aktuelle Ausgabehöhe |
| `format` | string | Ausgabeformat |
| `size_bytes` | int | Binärgröße in Bytes |

### Fehler-Antwort

```json
{
  "ok": false,
  "error": "resvg ist nicht installiert (pip install resvg)"
}
```

---

## MCP-Integration

Verwenden Sie Claude Desktop, um eine SVG → img2img-Pipeline zu erstellen:

```
# Schritt 1: Rasterisieren Sie das SVG
svg_rasterize(file_id=123, width=832, height=1216, background="#ffffff")

# Schritt 2: Übergeben Sie das zurückgegebene Base64 an img2img
nai_generate(prompt="icon, detailed illustration, ...", image=<base64>, strength=0.7)
```

### MCP-Tools

| Tool | Beschreibung |
|------|-------------|
| `svg_info` | Rasterisierungs-Verfügbarkeit prüfen |
| `svg_rasterize` | SVG zu PNG/WebP rasterisieren |

---

## Abhängigkeiten

| Paket | Lizenz | Zweck |
|---------|---------|---------|
| `resvg` | MIT | Rust-basierter SVG-Renderer (plattformübergreifend) |

Wenn `resvg` nicht installiert ist, zeigen Miniaturen einen Platzhalter und die API gibt HTTP 501 zurück.

```bash
pip install resvg
```
