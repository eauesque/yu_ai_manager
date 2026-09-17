# API di rasterizzazione SVG

API per la conversione delle immagini vettoriali SVG in bitmap PNG/WebP.
Progettato per l'integrazione della pipeline img2img — i dati dell'immagine base64 restituiti possono essere passati direttamente a NovelAI Bridge o SD WebUI Bridge.

## GET /api/svg/info

Verifica la disponibilità della rasterizzazione SVG.

- **Limite di velocità**: Nessuno (GET)

### Risposta

```json
{
  "available": true,
  "backend": "resvg"
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `available` | bool | Se la rasterizzazione è disponibile |
| `backend` | string \| null | Backend attivo (`"resvg"` o `null`) |

---

## POST /api/svg/rasterize

Rasterizza un SVG in un bitmap PNG/WebP.

- **Limite di velocità**: HEAVY

### Corpo della richiesta

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|-------------|-------------|
| `file_id` | int | *1 | ID file SVG dal database |
| `svg_path` | string | *1 | Percorso assoluto a un file SVG |
| `svg_data` | string | *1 | Stringa XML SVG inline |
| `width` | int | No | Larghezza di output (predefinito: 1024) |
| `height` | int | No | Altezza di output (predefinito: 1024) |
| `format` | string | No | `"png"` o `"webp"` (predefinito: `"png"`) |
| `background` | string | No | Colore di sfondo (es. `"#ffffff"`). Trasparente se omesso |

> *1: Fornisci esattamente uno di `file_id`, `svg_path`, o `svg_data`.

### Esempio di richiesta

```json
{
  "file_id": 123,
  "width": 832,
  "height": 1216,
  "format": "png",
  "background": "#ffffff"
}
```

### Risposta

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

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `ok` | bool | Flag di successo |
| `base64` | string | Dati PNG/WebP codificati in base64 |
| `width` | int | Larghezza di output effettiva |
| `height` | int | Altezza di output effettiva |
| `format` | string | Formato di output |
| `size_bytes` | int | Dimensione binaria in byte |

### Risposta di errore

```json
{
  "ok": false,
  "error": "resvg is not installed (pip install resvg)"
}
```

---

## Integrazione MCP

Usa Claude Desktop per costruire una pipeline SVG → img2img:

```
# Passaggio 1: Rasterizza l'SVG
svg_rasterize(file_id=123, width=832, height=1216, background="#ffffff")

# Passaggio 2: Passa il base64 restituito a img2img
nai_generate(prompt="icon, detailed illustration, ...", image=<base64>, strength=0.7)
```

### Strumenti MCP

| Strumento | Descrizione |
|------|-------------|
| `svg_info` | Controlla la disponibilità della rasterizzazione |
| `svg_rasterize` | Rasterizza SVG a PNG/WebP |

---

## Dipendenze

| Pacchetto | Licenza | Scopo |
|---------|---------|---------|
| `resvg` | MIT | Renderer SVG basato su Rust (multipiattaforma) |

Se `resvg` non è installato, le miniature mostrano un placeholder e l'API restituisce HTTP 501.

```bash
pip install resvg
```
