# API Tag

API per operazioni batch di tag e suggerimento/completamento automatico di tag.

## POST /api/tags/batch-set

Aggiungi o rimuovi tag da più file in una singola richiesta.

### Limite di velocità

WRITE (~120 req/min, burst 30)

### Corpo della richiesta

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|-------------|-------------|
| `items` | array | Sì | Elenco di operazioni (max 500 elementi) |
| `items[].file_id` | int | Sì | ID file (numero intero positivo) |
| `items[].add` | string[] | No | Nomi tag da aggiungere |
| `items[].remove` | string[] | No | Nomi tag da rimuovere |

- Ogni elemento richiede almeno uno di `add` o `remove`
- I tag che non esistono vengono creati automaticamente (namespace=null)
- I tag aggiunti tramite API hanno la loro fonte impostata su `"user"`
- I tag orfani (nessuna associazione file rimanente) vengono eliminati automaticamente

### Esempio di richiesta

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

### Risposta

```json
{
  "total": 1,
  "succeeded": 1,
  "failed": 0,
  "errors": []
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `total` | int | Numero totale di elementi elaborati |
| `succeeded` | int | Numero di operazioni riuscite |
| `failed` | int | Numero di operazioni non riuscite |
| `errors` | array | Elenco di dettagli errore |

### Errori

| Stato | Descrizione |
|--------|-------------|
| 400 | Corpo della richiesta non valido (elementi vuoti, file_id non valido, add/remove mancante, ecc.) |
| 429 | Limite di velocità superato |

---

## GET /api/tags/suggest

Restituisce candidati tag corrispondenti a una stringa di ricerca parziale. Destinato al completamento automatico.

### Parametri

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|-------------|-------------|
| `q` | string | Sì | Stringa di ricerca |
| `limit` | int | No | Numero massimo di risultati (predefinito: 20, max: 100) |

- La ricerca non fa distinzione tra maiuscole e minuscole (LIKE %q%)
- I risultati sono ordinati per `file_count` in ordine decrescente
- Una `q` vuota restituisce un array vuoto

### Risposta

```json
{
  "data": [
    { "id": 1, "tag": "landscape", "namespace": null, "file_count": 150 },
    { "id": 2, "tag": "1girl", "namespace": null, "file_count": 3420 }
  ]
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `data[].id` | int | ID tag |
| `data[].tag` | string | Nome tag |
| `data[].namespace` | string\|null | Namespace (di solito null) |
| `data[].file_count` | int | Numero di file associati a questo tag |
