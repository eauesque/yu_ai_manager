# API OCR

API per l'estrazione di testo (OCR) da immagini, video e PDF, insieme a traduzione, generazione di immagini di sovrapposizione, esportazione, benchmarking e gestione dei motori.

## POST /api/ocr/<file_id>

Esegui OCR su un file singolo e salva il risultato nel database.

### Limite di Velocità

WRITE

### Richiesta

```json
{
  "task": "ocr",
  "language": "auto",
  "server_id": ""
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | ID file (parametro di percorso) |
| `task` | string | No | Tipo di attività OCR. Uno di `ocr` / `ocr_document` / `ocr_manga`. Predefinito: `ocr` |
| `language` | string | No | Suggerimento di lingua. Predefinito: `auto` |
| `server_id` | string | No | ID del server di analisi da utilizzare. Auto-selezionato se omesso |

### Risposta (200)

```json
{
  "file_id": 42,
  "engine": "gemini-2.0-flash",
  "task": "ocr",
  "full_text": "Extracted text...",
  "language": "ja",
  "regions_count": 3,
  "row_id": 1
}
```

### Errori

- `400` — Valore task non valido
- `404` — File non trovato
- `500` — Errore di risoluzione del motore OCR / Errore di esecuzione OCR

---

## GET /api/ocr/result/<file_id>

Recupera un risultato OCR salvato.

### Parametri

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | ID file (parametro di percorso) |
| `task` | string | No | Filtra per tipo di attività |
| `engine` | string | No | Filtra per nome del motore |
| `all` | string | No | Se impostato a qualsiasi valore, restituisce tutti i risultati |

### Risposta (risultato trovato)

```json
{
  "file_id": 42,
  "task": "ocr",
  "engine": "gemini-2.0-flash",
  "full_text": "Extracted text...",
  "language": "ja",
  "regions": [...]
}
```

### Risposta (con `?all=1`)

```json
{
  "file_id": 42,
  "results": [
    { "task": "ocr", "engine": "gemini-2.0-flash", "full_text": "..." },
    { "task": "ocr_manga", "engine": "manga-ocr", "full_text": "..." }
  ]
}
```

### Risposta (nessun risultato)

```json
{
  "status": "not_found"
}
```

---

## DELETE /api/ocr/result/<file_id>

Cancella i risultati OCR salvati.

### Limite di Velocità

WRITE

### Richiesta

```json
{
  "task": "",
  "engine": ""
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | ID file (parametro di percorso) |
| `task` | string | No | Filtra per tipo di attività. Una stringa vuota prende di mira tutte le attività |
| `engine` | string | No | Filtra per nome del motore. Una stringa vuota prende di mira tutti i motori |

### Risposta

```json
{
  "deleted": 2
}
```

---

## POST /api/ocr/batch

Esegui OCR su più file in batch.

### Limite di Velocità

WRITE

### Richiesta

```json
{
  "file_ids": [1, 2, 3],
  "task": "ocr",
  "language": "auto",
  "server_id": ""
}
```

| Parametro | Tipo | Obbligatorio | Limite | Descrizione |
|-----------|------|----------|-------|-------------|
| `file_ids` | int[] | Yes | Max 500 | Array degli ID file target |
| `task` | string | No | — | Tipo di attività OCR. `ocr` / `ocr_document` / `ocr_manga`. Predefinito: `ocr` |
| `language` | string | No | — | Suggerimento di lingua. Predefinito: `auto` |
| `server_id` | string | No | — | ID del server di analisi da utilizzare |

### Risposta (200)

```json
{
  "processed": 2,
  "errors": 1,
  "results": [
    { "file_id": 1, "full_text_length": 128, "regions_count": 3 },
    { "file_id": 2, "full_text_length": 256, "regions_count": 5 }
  ],
  "error_details": [
    { "file_id": 3, "error": "File not found" }
  ]
}
```

### Errori

- `400` — `file_ids` è vuoto / supera 500 / valore task non valido
- `500` — Errore di risoluzione del motore OCR

---

## POST /api/ocr/video/<file_id>

Estrai fotogrammi chiave da un file video ed esegui OCR su ogni fotogramma.

### Limite di Velocità

WRITE

### Richiesta

```json
{
  "task": "ocr",
  "language": "auto",
  "server_id": "",
  "keyframe_count": 4,
  "strategy": "uniform"
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | ID file (parametro di percorso) |
| `task` | string | No | Tipo di attività OCR. Predefinito: `ocr` |
| `language` | string | No | Suggerimento di lingua. Predefinito: `auto` |
| `server_id` | string | No | ID del server di analisi da utilizzare |
| `keyframe_count` | int | No | Numero di fotogrammi chiave da estrarre. Intervallo: 1-16. Predefinito: `4` |
| `strategy` | string | No | Strategia di estrazione dei fotogrammi chiave. Predefinito: `uniform` |

### Risposta (200)

```json
{
  "file_id": 42,
  "engine": "gemini-2.0-flash",
  "task": "ocr",
  "full_text": "Text extracted from frames...",
  "frame_count": 4,
  "row_id": 5
}
```

### Errori

- `400` — File non è un video
- `404` — File non trovato
- `500` — Errore di risoluzione del motore OCR / Errore di esecuzione OCR video

---

## POST /api/ocr/pdf/<file_id>

Converti le pagine PDF in immagini ed esegui OCR. Utile per PDF scansionati senza livello di testo.

### Limite di Velocità

WRITE

### Richiesta

```json
{
  "task": "ocr_document",
  "language": "auto",
  "server_id": "",
  "page_range": "",
  "dpi": 200
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | ID file (parametro di percorso) |
| `task` | string | No | Tipo di attività OCR. Predefinito: `ocr_document` |
| `language` | string | No | Suggerimento di lingua. Predefinito: `auto` |
| `server_id` | string | No | ID del server di analisi da utilizzare |
| `page_range` | string | No | Intervallo di pagine (es. `"1-5"`, `"1,3,5"`). Una stringa vuota significa tutte le pagine |
| `dpi` | int | No | Risoluzione di rendering. Intervallo: 72-400. Predefinito: `200` |

### Risposta (200)

```json
{
  "file_id": 42,
  "engine": "gemini-2.0-flash",
  "task": "ocr_document",
  "full_text": "Text extracted from PDF...",
  "page_count": 10,
  "row_id": 6
}
```

### Errori

- `400` — File non è un PDF
- `404` — File non trovato
- `500` — Errore di risoluzione del motore OCR / Errore di esecuzione OCR PDF

---

## POST /api/ocr/bbox/<file_id>

Rileva i riquadri di delimitazione del testo per i risultati OCR esistenti. Utilizzato come secondo passaggio per aggiungere informazioni sulla posizione alle regioni di testo estratte in precedenza.

### Limite di Velocità

WRITE

### Richiesta

```json
{
  "task": "",
  "server_id": ""
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | ID file (parametro di percorso) |
| `task` | string | No | Tipo di attività OCR target |
| `server_id` | string | No | ID del server di analisi da utilizzare |

### Risposta (200)

```json
{
  "file_id": 42,
  "total_regions": 5,
  "detected_bboxes": 4,
  "regions": [
    {
      "id": 0,
      "text": "Text region",
      "bbox": { "x": 10, "y": 20, "width": 200, "height": 30 }
    }
  ]
}
```

### Errori

- `400` — Nessuna regione di testo trovata / Engine VLM richiesto
- `404` — Risultato OCR non trovato (esegui prima OCR) / File non trovato
- `500` — Errore di risoluzione del motore OCR / Errore di rilevamento bbox

---

## GET /api/ocr/engines

Elenca i motori OCR disponibili (server di analisi) con punteggi per attività.

### Parametri

Nessuno

### Risposta

```json
{
  "engines": [
    {
      "server_id": "server-1",
      "server_name": "Gemini Flash",
      "model": "gemini-2.0-flash",
      "type": "google",
      "scores": {
        "ocr": 85,
        "ocr_document": 90,
        "ocr_manga": 60
      }
    }
  ],
  "manga_ocr_available": false
}
```

---

## GET /api/ocr/npu

Ottieni lo stato del dispositivo NPU (Neural Processing Unit) e le impostazioni di ottimizzazione consigliate.

### Parametri

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `task` | string | No | Tipo di attività per raccomandazioni di ottimizzazione. Predefinito: `ocr` |

### Risposta

```json
{
  "npu": {
    "available": true,
    "device": "Hailo-10H",
    "driver_version": "4.20.0"
  },
  "optimization": {
    "recommended_batch_size": 4,
    "use_npu": true
  }
}
```

---

## POST /api/ocr/translate/<file_id>

Traduci un risultato OCR esistente nella lingua specificata. La traduzione viene salvata nel database.

### Limite di Velocità

WRITE

### Richiesta

```json
{
  "target_lang": "en",
  "server_id": "",
  "task": ""
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | ID file (parametro di percorso) |
| `target_lang` | string | Yes | Codice della lingua di destinazione (es. `en`, `ja`, `zh`, `ko`) |
| `server_id` | string | No | ID del server di analisi da utilizzare |
| `task` | string | No | Tipo di attività OCR target |

### Risposta (200)

```json
{
  "file_id": 42,
  "target_lang": "en",
  "translated_text": "Translated full text...",
  "engine": "gemini-2.0-flash",
  "region_translations": [
    { "region_id": 0, "original": "Original text", "translated": "Translated text" }
  ]
}
```

### Errori

- `400` — `target_lang` non specificato
- `404` — Risultato OCR non trovato
- `500` — Errore di esecuzione della traduzione

---

## GET /api/ocr/translations/<file_id>

Ottieni l'elenco dei risultati di traduzione per un file.

### Parametri

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | ID file (parametro di percorso) |
| `target_lang` | string | No | Filtra per codice della lingua |

### Risposta

```json
{
  "file_id": 42,
  "translations": [
    {
      "target_lang": "en",
      "translated_text": "Translated text...",
      "engine": "gemini-2.0-flash",
      "region_translations": [...]
    }
  ]
}
```

---

## GET /api/ocr/overlay/<file_id>

Genera un'immagine di sovrapposizione con i risultati OCR (o traduzioni) resi sopra l'immagine originale.

### Parametri

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | ID file (parametro di percorso) |
| `mode` | string | No | Modalità di visualizzazione. `translated` / `original` / `both`. Predefinito: `translated` |
| `target_lang` | string | No | Filtra per lingua di traduzione |
| `format` | string | No | Formato dell'immagine di output. `png` / `jpeg`. Predefinito: `png` |
| `task` | string | No | Tipo di attività OCR target |

### Risposta

- Content-Type: `image/png` o `image/jpeg`
- Filename: `ocr_overlay_{file_id}.{ext}`

### Errori

- `400` — Valore mode / format non valido
- `404` — Risultato OCR non trovato / File non trovato
- `500` — Errore di generazione immagine di sovrapposizione

---

## GET /api/ocr/export/<file_id>

Esporta un risultato OCR nel formato specificato come download di file.

### Parametri

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | ID file (parametro di percorso) |
| `format` | string | No | Formato di esportazione. `txt` / `md` / `json` / `pdf`. Predefinito: `md` |
| `task` | string | No | Tipo di attività OCR target |
| `include_translation` | string | No | Se impostato a qualsiasi valore, include le traduzioni |
| `target_lang` | string | No | Codice della lingua della traduzione da includere |

### Risposta

- Content-Type: Tipo MIME appropriato al formato
- Content-Disposition: `attachment; filename=...`

### Errori

- `400` — Valore format non valido
- `404` — Risultato OCR non trovato

---

## POST /api/ocr/export/batch

Esporta i risultati OCR per più file in batch. Supporta il download ZIP o il salvataggio diretto lato server.

### Limite di Velocità

WRITE

### Richiesta

```json
{
  "file_ids": [1, 2, 3],
  "format": "md",
  "output_dir": "",
  "overlay_mode": "translated",
  "target_lang": "",
  "include_translation": false
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `file_ids` | int[] | Yes | Array degli ID file target |
| `format` | string | No | Formato di esportazione. `txt` / `md` / `json` / `pdf` / `overlay`. Impostazioni predefinite dalla configurazione dell'estensione |
| `output_dir` | string | No | Percorso assoluto per il salvataggio lato server. Se omesso, restituisce il download ZIP |
| `overlay_mode` | string | No | Modalità di sovrapposizione (quando `format=overlay`). `translated` / `original` / `both`. Predefinito: `translated` |
| `target_lang` | string | No | Codice della lingua di traduzione |
| `include_translation` | bool | No | Se includere le traduzioni. Predefinito: `false` |

### Risposta (download ZIP)

- Content-Type: `application/zip`
- Filename: `ocr_export_batch.zip` (formati testo) o `ocr_overlay_batch.zip` (formato overlay)

### Risposta (salvataggio lato server)

```json
{
  "saved": 3,
  "errors": 0,
  "output_dir": "/path/to/output",
  "results": [
    { "file_id": 1, "path": "/path/to/output/ocr_1.md" }
  ],
  "error_details": []
}
```

### Errori

- `400` — `file_ids` è vuoto / valore format non valido / `output_dir` non è un percorso assoluto
- `403` — `output_dir` è una directory vietata
- `404` — Nessun risultato OCR trovato

---

## POST /api/ocr/benchmark

Esegui un benchmark OCR per misurare l'accuratezza e le prestazioni. Richiede casi di benchmark (coppie immagine + testo di base).

### Limite di Velocità

WRITE

### Richiesta

```json
{
  "task": "ocr",
  "server_id": "",
  "benchmark_dir": ""
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `task` | string | No | Tipo di attività da sottoporre a benchmark. Predefinito: `ocr` |
| `server_id` | string | No | ID del server di analisi da utilizzare |
| `benchmark_dir` | string | No | Percorso della directory per i casi di benchmark. Predefinito: `extensions/builtin_ocr/benchmarks/` |

### Risposta (200)

```json
{
  "total_cases": 10,
  "avg_accuracy": 0.92,
  "avg_time_ms": 1500,
  "results": [
    {
      "image": "test1.png",
      "accuracy": 0.95,
      "time_ms": 1200
    }
  ]
}
```

### Errori

- `404` — Nessun caso di benchmark trovato
- `500` — Errore di risoluzione del motore OCR / Errore di esecuzione benchmark

---

## GET /api/ocr/benchmark/cases

Elenca i casi di benchmark disponibili.

### Parametri

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `dir` | string | No | Percorso della directory per i casi di benchmark |

### Risposta

```json
{
  "cases": [
    {
      "image": "test1.png",
      "task": "ocr",
      "language": "ja",
      "expected_length": 256,
      "tags": ["manga", "vertical"]
    }
  ],
  "total": 10
}
```

---

## GET /api/ocr/profiles

Elenca i profili dei modelli OCR con configurazioni di punteggio per attività.

### Parametri

Nessuno

### Risposta

```json
{
  "profiles": [
    {
      "model_prefix": "gemini-2.0-flash",
      "scores": {
        "ocr": 85,
        "ocr_document": 90,
        "ocr_manga": 60
      }
    }
  ]
}
```

---

## POST /api/ocr/profiles/fetch

Recupera e unisci i profili dei modelli pubblicati dalla comunità da un URL.

### Limite di Velocità

WRITE

### Richiesta

```json
{
  "url": "https://example.com/ocr-profiles.json"
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `url` | string | Yes | URL del JSON del profilo |

### Risposta (200)

```json
{
  "added": 3,
  "updated": 1,
  "total": 15
}
```

### Errori

- `400` — `url` non specificato
- `500` — Errore di recupero o unione

---

## PUT /api/ocr/profiles/<model_prefix>

Aggiorna manualmente i punteggi per un profilo del modello.

### Limite di Velocità

WRITE

### Richiesta

```json
{
  "scores": {
    "ocr": 90,
    "ocr_document": 85,
    "ocr_manga": 70
  }
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `model_prefix` | string | Yes | Prefisso del nome del modello (parametro di percorso) |
| `scores` | object | Yes | Oggetto con tipi di attività come chiavi e punteggi (interi) come valori |

### Risposta

```json
{
  "model": "gemini-2.0-flash",
  "scores": {
    "ocr": 90,
    "ocr_document": 85,
    "ocr_manga": 70
  }
}
```

### Errori
