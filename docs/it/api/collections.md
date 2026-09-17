# API Raccolte

API per la gestione delle raccolte (gruppi preferiti).

## GET /api/collections

Elenca tutte le raccolte. Ordinate per `sort_order` ASC, quindi `id` ASC.

### Parametri

Nessuno

### Risposta

```json
{
  "collections": [
    {
      "id": 1,
      "name": "Favorites",
      "sort_order": 0,
      "created_at": 1709500000,
      "count": 42,
      "is_smart": false,
      "query_json": null
    }
  ]
}
```

## POST /api/collections

Crea una nuova raccolta.

### Limite di velocità

WRITE

### Richiesta

```json
{
  "name": "My Collection",
  "query_json": null
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|-------------|-------------|
| `name` | string | Sì | Nome della raccolta |
| `query_json` | object/null | No | Query per raccolte intelligenti. Ometti per raccolte normali |

### Risposta (201)

```json
{
  "id": 2,
  "name": "My Collection",
  "is_smart": false
}
```

## PUT /api/collections/<id>

Rinomina una raccolta.

### Limite di velocità

WRITE

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `id` | int | ID raccolta (parametro di percorso) |

### Richiesta

```json
{
  "name": "Renamed Collection"
}
```

### Risposta

```json
{
  "id": 2,
  "name": "Renamed Collection"
}
```

## DELETE /api/collections/<id>

Elimina una raccolta. Tutte le voci preferite nella raccolta vengono eliminate anche loro.

La raccolta predefinita (`id=1`) non può essere eliminata.

### Limite di velocità

WRITE

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `id` | int | ID raccolta (parametro di percorso) |

### Risposta

```json
{
  "deleted": 2
}
```

## POST /api/collections/reorder

Modifica l'ordine di visualizzazione delle raccolte.

### Limite di velocità

WRITE

### Richiesta

```json
{
  "ids": [3, 1, 2]
}
```

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `ids` | int[] | Array di ID raccolta. L'ordine specificato diventa il nuovo ordine di ordinamento |

### Risposta

```json
{
  "ok": true
}
```

## POST /api/collections/<id>/batch-add

Aggiungi file a una raccolta in massa. Idempotente: le voci già esistenti vengono saltate e conteggiate come successi.

### Limite di velocità

WRITE

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `id` | int | ID raccolta (parametro di percorso) |

### Richiesta

```json
{
  "file_ids": [1, 2, 3]
}
```

| Parametro | Tipo | Limite | Descrizione |
|-----------|------|-------|-------------|
| `file_ids` | int[] | Max 500 | Array di ID file da aggiungere |

### Risposta

```json
{
  "total": 3,
  "succeeded": 3,
  "failed": 0,
  "errors": []
}
```

## POST /api/collections/<id>/batch-remove

Rimuovi file da una raccolta in massa.

### Limite di velocità

WRITE

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `id` | int | ID raccolta (parametro di percorso) |

### Richiesta

```json
{
  "file_ids": [1, 2]
}
```

| Parametro | Tipo | Limite | Descrizione |
|-----------|------|-------|-------------|
| `file_ids` | int[] | Max 500 | Array di ID file da rimuovere |

### Risposta

```json
{
  "total": 2,
  "succeeded": 2,
  "failed": 0,
  "errors": []
}
```

## GET /api/collections/<id>/export/csv

Esporta i file in una raccolta come CSV.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `id` | int | ID raccolta (parametro di percorso) |

### Risposta

- Content-Type: `text/csv; charset=utf-8`
- Colonne CSV: `id`, `filename`, `folder`, `path`, `meta_source`, `mtime`, `positive`, `negative`
- Restituisce 404 se la raccolta non viene trovata
