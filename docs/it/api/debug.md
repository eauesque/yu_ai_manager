# API Debug

API interne per il debug e la diagnostica. Utilizzate per ispezionare i metadati dei file, verificare le informazioni del modello e gestire le directory delle radici scansionate.

Questi endpoint non hanno WebUI frontend e sono principalmente destinati allo sviluppo e alla risoluzione dei problemi.

## GET /api/debug/file-meta/<file_id>

Ispeziona i metadati dettagliati di un file. Restituisce i metadati archiviati nel DB, e per i file all'interno di archivi ZIP, restituisce anche i risultati estratti di recente.

### Autenticazione

Sessione PIN o chiave API

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `file_id` | int | ID file (parametro di percorso) |

### Risposta

```json
{
  "id": 123,
  "path": "/images/sample.png",
  "meta_source": "a1111_png",
  "parser_version": 5,
  "format": "a1111",
  "model_name": "sd_xl_base_1.0",
  "raw_prompt_length": 256,
  "raw_prompt_preview": "masterpiece, best quality, ...",
  "raw_negative_preview": "lowres, bad anatomy, ...",
  "raw_meta_json_length": 1024,
  "raw_meta_json_preview": "{\"steps\": 20, ...}",
  "has_v4_prompt": false,
  "has_comment": true
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `id` | int | ID file |
| `path` | string | Percorso del file |
| `meta_source` | string | Fonte dei metadati (`a1111_png`, `novelai_v4_png`, ecc.) |
| `parser_version` | int | Versione del parser |
| `format` | string | Formato del modello |
| `model_name` | string/null | Nome del modello |
| `raw_prompt_length` | int | Conteggio dei caratteri del prompt grezzo |
| `raw_prompt_preview` | string | Primi 300 caratteri del prompt grezzo |
| `raw_negative_preview` | string | Primi 300 caratteri del prompt negativo |
| `raw_meta_json_length` | int | Conteggio dei caratteri del JSON dei metadati grezzi |
| `raw_meta_json_preview` | string | Primi 500 caratteri del JSON dei metadati grezzi |
| `has_v4_prompt` | bool | Se contiene un prompt NovelAI V4 |
| `has_comment` | bool | Se contiene un campo Comment |

Per i file all'interno di archivi ZIP, viene aggiunto un campo `fresh_extract` con i risultati dell'estrazione:

```json
{
  "fresh_extract": {
    "meta_source": "a1111_png",
    "format": "a1111",
    "raw_meta_json_length": 1024,
    "raw_meta_json_preview": "{...}",
    "has_v4_prompt": false,
    "success": true,
    "raw_prompt_preview": "masterpiece, ..."
  }
}
```

### Errori

| Stato | Descrizione |
|--------|-------------|
| 404 | File non trovato |

## GET /api/debug/model-check

Verifica lo stato di archiviazione di `model_name` nella tabella dei modelli. Restituisce statistiche e campioni per i record con e senza nomi di modelli.

### Autenticazione

Sessione PIN o chiave API

### Parametri

Nessuno

### Risposta

```json
{
  "total_templates": 1000,
  "with_model_name": 850,
  "without_model_name": 150,
  "samples_with_model": [
    {
      "file_id": 1,
      "model_name": "sd_xl_base_1.0",
      "model_hash": "abc123",
      "format": "a1111"
    }
  ],
  "samples_without_model": [
    {
      "file_id": 42,
      "model_name": null,
      "format": "comfy",
      "raw_meta_json_preview": "{...}"
    }
  ]
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `total_templates` | int | Numero totale di modelli |
| `with_model_name` | int | Numero di record con il nome del modello impostato |
| `without_model_name` | int | Numero di record senza il nome del modello |
| `samples_with_model` | array | Campioni con il nome del modello (fino a 10) |
| `samples_without_model` | array | Campioni senza il nome del modello (fino a 5) |

## GET /api/scanned-roots

Estrai le directory radice dai file registrati nel DB e restituiscili con i conteggi dei file. Aggrega sia le radici di scansione configurate che le radici dei file che non appartengono a nessuna radice configurata.

### Autenticazione

Sessione PIN o chiave API

### Parametri

Nessuno

### Risposta

```json
{
  "roots": [
    {
      "path": "C:\\Images\\AI",
      "count": 5000
    },
    {
      "path": "D:\\Archives",
      "count": 1200
    }
  ]
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `roots` | array | Array di directory radice (ordinate per conteggio file decrescente, max 50) |
| `roots[].path` | string | Percorso della directory |
| `roots[].count` | int | Numero di file sotto questo percorso |

### Errori

| Stato | Descrizione |
|--------|-------------|
| 500 | Errore nel calcolo della sintesi delle radici |

## POST /api/debug/query

Esegui una query SQL di sola lettura. Richiede la variabile d'ambiente `YU_DEBUG_MODE=1` e consente solo l'accesso da localhost.

### Limite di Velocità

WRITE

### Autenticazione

Sessione PIN o chiave API (solo localhost + `YU_DEBUG_MODE=1`)

### Richiesta

```json
{
  "sql": "SELECT id, path, meta_source FROM files LIMIT 10",
  "limit": 100
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `sql` | string | Yes | Istruzione SELECT da eseguire |
| `limit` | int | No | Numero massimo di righe da restituire (predefinito: 100, max: 10000) |

### Vincoli

- Solo le istruzioni SELECT sono consentite (INSERT, UPDATE, DELETE, ecc. sono rifiutate)
- Le istruzioni multiple (separate da punto e virgola) non sono consentite
- Le query contenenti parole chiave di scrittura (DROP, ALTER, CREATE, ecc.) sono rifiutate

### Risposta

```json
{
  "columns": ["id", "path", "meta_source"],
  "rows": [
    {"id": 1, "path": "/images/test.png", "meta_source": "a1111_png"}
  ],
  "row_count": 1,
  "truncated": false
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `columns` | string[] | Array di nomi di colonne |
| `rows` | object[] | Righe di risultati (ogni riga è un oggetto chiave per nome di colonna) |
| `row_count` | int | Numero di righe restituite |
| `truncated` | bool | `true` se i risultati sono stati troncati dal limite |

### Errori

| Stato | Descrizione |
|--------|-------------|
| 400 | SQL vuoto, istruzioni multiple, query non-SELECT, contiene operazioni di scrittura, errore di sintassi SQL |
| 403 | Modalità debug non abilitata, o accesso da non-localhost |

## POST /api/scanned-roots/purge

Elimina definitivamente tutti i record di file sotto il percorso specificato dal DB. I record correlati (tag, modelli, ecc.) vengono eliminati a cascata. I tag non utilizzati vengono automaticamente eliminati.

### Limite di Velocità

DESTRUCTIVE

### Autenticazione

Sessione PIN o chiave API

### Richiesta

```json
{
  "path": "C:\\Images\\OldFolder"
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `path` | string | Yes | Percorso della radice da eliminare. Tutti i file sotto questo percorso verranno eliminati |

### Risposta

```json
{
  "purged": 150,
  "path": "C:\\Images\\OldFolder"
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `purged` | int | Numero di record di file eliminati |
| `path` | string | Il percorso specificato |

### Errori

| Stato | Descrizione |
|--------|-------------|
| 400 | Percorso non specificato |
| 500 | Operazione di eliminazione fallita |
