# API di analisi video

API per la gestione della configurazione dell'analisi video e il controllo dello stato. Controlla le impostazioni per l'estrazione di keyframe dai file video.

## GET /api/video-analysis/config

Ottieni la configurazione dell'analisi video attuale. Restituisce le impostazioni salvate unite ai valori predefiniti.

### Parametri

Nessuno

### Risposta

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

| Campo | Tipo | Predefinito | Descrizione |
|-------|------|---------|-------------|
| `enabled` | boolean | `true` | Se l'analisi video è abilitata |
| `keyframe_count` | int | `4` | Numero di keyframe da estrarre (1-16) |
| `strategy` | string | `"uniform"` | Strategia di estrazione dei keyframe. `uniform` (equidistanti), `scene` (rilevamento dei cambi scena), `single` (fotogramma singolo) |
| `scene_threshold` | float | `0.4` | Soglia di rilevamento della scena (0.0-1.0). Usato quando `strategy` è `scene` |
| `store_per_keyframe` | boolean | `false` | Se memorizzare ogni keyframe individualmente |

## POST /api/video-analysis/config

Salva la configurazione dell'analisi video. Solo i campi specificati vengono aggiornati; i campi omessi conservano i loro valori esistenti.

### Limite di velocità

WRITE

### Richiesta

```json
{
  "enabled": true,
  "keyframe_count": 8,
  "strategy": "scene",
  "scene_threshold": 0.3,
  "store_per_keyframe": false
}
```

Tutti i campi sono opzionali. Solo i campi specificati vengono aggiornati.

| Parametro | Tipo | Obbligatorio | Vincoli | Descrizione |
|-----------|------|----------|-------------|-------------|
| `enabled` | boolean | No | - | Se l'analisi video è abilitata |
| `keyframe_count` | int | No | 1-16 | Numero di keyframe da estrarre |
| `strategy` | string | No | `uniform`, `scene`, o `single` | Strategia di estrazione dei keyframe |
| `scene_threshold` | float | No | 0.0-1.0 | Soglia di rilevamento della scena |
| `store_per_keyframe` | boolean | No | - | Se memorizzare ogni keyframe individualmente |

### Risposta

Restituisce la configurazione unita dopo il salvataggio (stesso formato di GET).

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

### Errori

| Stato | Codice | Condizione |
|--------|--------|-----------|
| 400 | `invalid_json` | Il corpo della richiesta non è un oggetto JSON |
| 400 | `invalid_value` | Errore di convalida (tipo errato, valore fuori intervallo, strategia non valida, ecc.) |

## GET /api/video-analysis/status

Ottieni le informazioni sullo stato dell'analisi video. Restituisce la disponibilità di ffmpeg, il numero di file video e il numero di file con keyframe estratti.

### Parametri

Nessuno

### Risposta

```json
{
  "ffmpeg": true,
  "video_files": 150,
  "files_with_keyframes": 42
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `ffmpeg` | boolean | Se ffmpeg è disponibile nel sistema |
| `video_files` | int | Numero totale di file video nel database (escludendo soft-deleted). Estensioni supportate: `.mp4`, `.webm`, `.avi`, `.mov`, `.mkv`, `.m4v`, `.ogv` |
| `files_with_keyframes` | int | Numero di file che hanno keyframe estratti |
