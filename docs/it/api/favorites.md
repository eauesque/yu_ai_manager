# API Preferiti

API per aggiungere, rimuovere, controllare e elencare i preferiti.

## POST /api/favorites/toggle

Attiva/disattiva lo stato preferito di un file. Aggiunge il file se non è già preferito; lo rimuove se presente.

- **Limite di velocità**: WRITE

### Corpo della richiesta

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|-------------|-------------|
| `file_id` | int | Sì | ID file di destinazione (numero intero positivo) |
| `collection_id` | int | No | ID raccolta (predefinito: 1) |

```json
{
  "file_id": 42,
  "collection_id": 1
}
```

### Risposta

```json
{
  "file_id": 42,
  "collection_id": 1,
  "favorited": true
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `file_id` | int | ID file di destinazione |
| `collection_id` | int | ID raccolta |
| `favorited` | bool | Stato dopo l'attivazione/disattivazione. `true` = aggiunto, `false` = rimosso |

## GET /api/favorites/check

Restituisce quale dei file ID specificati sono preferiti.

### Parametri

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|-------------|-------------|
| `ids` | string | Sì | ID file separati da virgola (es. `1,2,3`) |
| `collection_id` | int | No | Filtra una raccolta specifica |

### Risposta

```json
{
  "favorites": [1, 3]
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `favorites` | int[] | Array di ID file che sono preferiti |

## GET /api/favorites/check_collections

Restituisce gli ID raccolta che contengono il file specificato.

### Parametri

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|-------------|-------------|
| `file_id` | int | Sì | ID file di destinazione |

### Risposta

```json
{
  "collections": [1, 3]
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `collections` | int[] | Array di ID raccolta contenenti questo file |

## GET /api/favorites/list

Recupera un elenco di ID file preferiti. I risultati sono ordinati per data di aggiunta in ordine decrescente. I file eliminati logicamente vengono esclusi.

### Parametri

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|-------------|-------------|
| `collection_id` | int | No | Filtra una raccolta specifica |

### Risposta

```json
{
  "ids": [42, 55, 67]
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `ids` | int[] | Array di ID file preferiti (ordinati per `added_at` DESC) |
