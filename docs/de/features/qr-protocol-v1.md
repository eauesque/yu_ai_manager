# YU QR Protokoll v1 — Einheitliche Nutzlast-Spezifikation

**Version:** 1.0
**Datum:** 2026-02-23
**Zielanwendung:** YU AI Manager (TagDB)

---

## Übersicht

YU AI Manager unterstützt Eingabeaufforderungs-Freigabe und Fehlerdiagnosen über QR-Codes. Dieses Dokument bietet eine einheitliche Spezifikation für das QR-Nutzlast-Format.

### Verwendete Bibliotheken

| Zweck | Bibliothek | Version |
|------|-----------|-----------|
| QR-Generierung | QRCode.js | 1.0.0 |
| QR-Lesevorgänge | jsQR | 1.4.0 |

### QR-Kapazitätsgrenzen

- Maximale Zeichen: **2.953** (Fehlerkorrektur-Level M)
- Über 2.500 Zeichen: Die Meta JSON wird minimiert und erneut versucht
- Über 2.953 Zeichen: Fehler (`qr.info.too_long`)

---

## Nutzlast-Typ 1 — Eingabeaufforderungs-Freigabe

### Ursprung

- `GET /api/share/<file_id>` -> Python `build_share_data_payload()`
- `routes/share_ops/payload_build.py`

### JSON-Schema

```json
{
  "v":   "1.0",
  "t":   "prompt",
  "p":   "<positive prompt>",
  "n":   "<negative prompt>",
  "src": "TagDB",
  "m":   "<model name>",
  "s":   "<seed>",
  "st":  "<steps>",
  "cfg": "<CFG scale>",
  "sa":  "<sampler>",
  "sz":  "<WxH>"
}
```

### Felddefinitionen

| Schlüssel | Typ | Erforderlich | Beschreibung | Limit |
|------|-----|------|------|------|
| `v` | string | ✅ | Protokoll-Version. Derzeit `"1.0"` | — |
| `t` | string | ✅ | Nutzlast-Typ. Derzeit immer `"prompt"` | — |
| `p` | string | ✅ | Positive Eingabeaufforderung | 2.000 chars |
| `n` | string | ✅ | Negative Eingabeaufforderung | 1.000 chars |
| `src` | string | ✅ | Aussteller-Kennung. Derzeit immer `"TagDB"` | — |
| `m` | string | — | Modellname | — |
| `s` | string | — | Seed-Wert | — |
| `st` | string | — | Schritt-Anzahl | — |
| `cfg` | string | — | CFG-Skalierung | — |
| `sa` | string | — | Sampler-Name | — |
| `sz` | string | — | Bildgröße im Format `"WxH"` | — |

---

## QR-Modi — 4 Typen

### `positive` Modus

```
qrText = shareData.p
```

- Inhalt: Nur Text der positiven Eingabeaufforderung
- Anwendungsfall: Direkte Text-Freigabe von Eingabeaufforderungen

### `negative` Modus

```
qrText = shareData.n
```

- Inhalt: Nur Text der negativen Eingabeaufforderung

### `meta` Modus

```
qrText = JSON.stringify(shareData, null, 0)
```

- Inhalt: Die gesamte Eingabeaufforderungs-Freigabe JSON-Nutzlast, kompakt
- Fallback zu hübsch-gedrucktem `JSON.stringify`, wenn das Ergebnis 2.500 Zeichen überschreitet

### `url` Modus

```
encoded = btoa(unescape(encodeURIComponent(JSON.stringify(shareData))))
qrText  = "{origin}/share?data={encoded}"
```

- Inhalt: Eine URL zur YU AI Manager Freigabe-Seite
- Deaktiviert auf localhost (`localhost` / `127.0.0.1`)

---

## Nutzlast-Typ 2 — Fehlerdiagnose

### Ursprung

- Generiert bei HTTP-Fehlern -> `_render_error_page()`
- `core/web/app_factory_handlers.py`

### JSON-Schema

```json
{
  "s": "<HTTP status code>",
  "p": "<request path>",
  "v": "<APP_VERSION>"
}
```

### Felddefinitionen

| Schlüssel | Typ | Beschreibung | Limit |
|------|-----|------|------|
| `s` | string | HTTP-Statuscode (`"404"`, `"500"`, usw.) | — |
| `p` | string | Anfrage-Pfad | 80 chars |
| `v` | string | Anwendungs-Version (aus `APP_VERSION` Datei) | — |

---

## URL-Freigabe Dekodierungs-Verfahren

Dekodierung auf der Freigabe-Seite (`/share?data=...`):

```javascript
const encoded = new URL(location).searchParams.get('data');
const json    = decodeURIComponent(escape(atob(encoded)));
const data    = JSON.parse(json);
```

---

## QR-Generierungs-Parameter

```javascript
new QRCode(container, {
  text:         qrText,
  width:        200,   // 180 auf Fehlerseiten
  height:       200,   // 180 auf Fehlerseiten
  colorDark:    '#000000',
  colorLight:   '#ffffff',
  correctLevel: QRCode.CorrectLevel.M,  // 15% Fehlerkorrektur
});
```

---

## Zukünftige Erweiterungen (v1.x)

| Feature | Status | Notizen |
|------|------|------|
| Sammlungs-QR-Export (mehrere Bilder) | Nicht implementiert | Geplant als Nutzlast-Typ 3 |
| `t: "collection"` Typ | Nicht definiert | Datei-ID Liste + Sammlungsname |
| Komprimierung (gzip + Base64) | Nicht implementiert | Alternative für Eingabeaufforderungen, die 2.953 Zeichen überschreiten |

---

## Implementierungs-Dateien

| Datei | Rolle |
|----------|------|
| `routes/share.py` | Share-API Blueprint |
| `routes/share_ops/payload_build.py` | Nutzlast-Generierung |
| `routes/share_ops/prompt_extract.py` | Eingabeaufforderungs-Daten-Extraktion |
| `core/web/app_factory_handlers.py` | Fehler QR-Daten-Generierung |
| `static/js/runtime/tools/runtime-tools-qr-core.js` | QR-Erstellung und Rendering |
| `static/js/runtime/tools/runtime-tools-qr.js` | QR-UI-Handler |
| `static/js/share/share-qr.js` | QR-Bild-Dekodierung |
| `static/js/share/share-page.js` | Freigabe-Seite Anzeige |
| `static/vendor/qrcode.min.js` | QRCode.js Bibliothek |
| `static/vendor/jsQR.min.js` | jsQR Bibliothek |
