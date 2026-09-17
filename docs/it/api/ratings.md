# API Valutazioni

API per la gestione delle valutazioni dei file (valutazioni da 1 a 5 stelle): impostazione, recupero e visualizzazione delle statistiche.

## POST /api/ratings/set

Imposta una valutazione per un file. Specifica `rating=0` per cancellare la valutazione.

**Limite di velocità**: WRITE

### Richiesta

```json
{
  "file_id": 42,
  "rating": 5
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|-------------|-------------|
| `file_id` | int | Sì | ID file (numero intero positivo) |
| `rating` | int | Sì | Valore di valutazione (0–5). 0 cancella la valutazione |

### Risposta

```json
{
  "file_id": 42,
  "rating": 5
}
```

## POST /api/ratings/batch-set

Imposta valutazioni per più file contemporaneamente.

**Limite di velocità**: WRITE

### Richiesta

```json
{
  "items": [
    { "file_id": 1, "rating": 5 },
    { "file_id": 2, "rating": 3 }
  ]
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|-------------|-------------|
| `items` | array | Sì | Elenco di voci di valutazione (max 500) |
| `items[].file_id` | int | Sì | ID file (numero intero positivo) |
| `items[].rating` | int | Sì | Valore di valutazione (0–5) |

### Risposta

```json
{
  "total": 2,
  "succeeded": 2,
  "failed": 0,
  "errors": []
}
```

## GET /api/ratings/get

Ottieni la valutazione per un file. Restituisce `rating: 0` se il file non è valutato.

### Parametri

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|-------------|-------------|
| `file_id` | int | Sì | ID file (parametro di query) |

### Risposta

```json
{
  "file_id": 42,
  "rating": 5
}
```

> **Nota**: I file senza valutazione restituiscono `rating: 0`.

## POST /api/ratings/batch

Recupera valutazioni per più file contemporaneamente.

### Richiesta

```json
{
  "file_ids": [1, 2, 3]
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|-------------|-------------|
| `file_ids` | array | Sì | Elenco di ID file |

### Risposta

```json
{
  "ratings": {
    "1": 5,
    "3": 4
  }
}
```

> **Nota**: Solo i file valutati vengono visualizzati nella mappa. I file senza valutazione vengono omessi dalla risposta.

## GET /api/ratings/stats

Ottieni statistiche di valutazione in tutti i file.

### Parametri

Nessuno.

### Risposta

```json
{
  "total_rated": 1234,
  "distribution": {
    "1": 50,
    "2": 100,
    "3": 300,
    "4": 500,
    "5": 284
  }
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `total_rated` | int | Numero totale di file valutati |
| `distribution` | object | Conteggio file per valore di valutazione (1–5) |
