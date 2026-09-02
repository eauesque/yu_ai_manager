# API Collections

API pour gérer les collections (groupes de favoris).

## GET /api/collections

Lister toutes les collections. Triées par `sort_order` ASC, puis `id` ASC.

### Paramètres

Aucun

### Réponse

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

Créer une nouvelle collection.

### Limitation de débit

WRITE

### Requête

```json
{
  "name": "My Collection",
  "query_json": null
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `name` | string | Oui | Nom de la collection |
| `query_json` | object/null | Non | Requête pour les collections intelligentes. Omettez pour les collections ordinaires |

### Réponse (201)

```json
{
  "id": 2,
  "name": "My Collection",
  "is_smart": false
}
```

## PUT /api/collections/<id>

Renommer une collection.

### Limitation de débit

WRITE

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `id` | int | ID de la collection (paramètre de chemin) |

### Requête

```json
{
  "name": "Renamed Collection"
}
```

### Réponse

```json
{
  "id": 2,
  "name": "Renamed Collection"
}
```

## DELETE /api/collections/<id>

Supprimer une collection. Tous les entrées de favoris dans la collection sont également supprimées.

La collection par défaut (`id=1`) ne peut pas être supprimée.

### Limitation de débit

WRITE

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `id` | int | ID de la collection (paramètre de chemin) |

### Réponse

```json
{
  "deleted": 2
}
```

## POST /api/collections/reorder

Modifier l'ordre d'affichage des collections.

### Limitation de débit

WRITE

### Requête

```json
{
  "ids": [3, 1, 2]
}
```

| Paramètre | Type | Description |
|-----------|------|-------------|
| `ids` | int[] | Tableau des ID de collection. L'ordre spécifié devient le nouvel ordre de tri |

### Réponse

```json
{
  "ok": true
}
```

## POST /api/collections/<id>/batch-add

Ajouter des fichiers à une collection en masse. Idempotent : les entrées qui existent déjà sont ignorées et comptées comme des succès.

### Limitation de débit

WRITE

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `id` | int | ID de la collection (paramètre de chemin) |

### Requête

```json
{
  "file_ids": [1, 2, 3]
}
```

| Paramètre | Type | Limite | Description |
|-----------|------|--------|-------------|
| `file_ids` | int[] | Max 500 | Tableau des ID de fichiers à ajouter |

### Réponse

```json
{
  "total": 3,
  "succeeded": 3,
  "failed": 0,
  "errors": []
}
```

## POST /api/collections/<id>/batch-remove

Supprimer des fichiers d'une collection en masse.

### Limitation de débit

WRITE

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `id` | int | ID de la collection (paramètre de chemin) |

### Requête

```json
{
  "file_ids": [1, 2]
}
```

| Paramètre | Type | Limite | Description |
|-----------|------|--------|-------------|
| `file_ids` | int[] | Max 500 | Tableau des ID de fichiers à supprimer |

### Réponse

```json
{
  "total": 2,
  "succeeded": 2,
  "failed": 0,
  "errors": []
}
```

## GET /api/collections/<id>/export/csv

Exporter les fichiers d'une collection en tant que CSV.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `id` | int | ID de la collection (paramètre de chemin) |

### Réponse

- Content-Type: `text/csv; charset=utf-8`
- Colonnes CSV : `id`, `filename`, `folder`, `path`, `meta_source`, `mtime`, `positive`, `negative`
- Retourne 404 si la collection n'est pas trouvée
