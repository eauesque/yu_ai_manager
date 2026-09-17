# API Évaluations

API pour gérer les évaluations de fichiers (évaluations de 1 à 5 étoiles) : définir, récupérer et afficher les statistiques.

## POST /api/ratings/set

Définir une évaluation pour un fichier. Spécifiez `rating=0` pour effacer l'évaluation.

**Limitation de débit** : WRITE

### Requête

```json
{
  "file_id": 42,
  "rating": 5
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `file_id` | int | Oui | ID du fichier (entier positif) |
| `rating` | int | Oui | Valeur d'évaluation (0–5). 0 efface l'évaluation |

### Réponse

```json
{
  "file_id": 42,
  "rating": 5
}
```

## POST /api/ratings/batch-set

Définir les évaluations pour plusieurs fichiers à la fois.

**Limitation de débit** : WRITE

### Requête

```json
{
  "items": [
    { "file_id": 1, "rating": 5 },
    { "file_id": 2, "rating": 3 }
  ]
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `items` | array | Oui | Liste des entrées d'évaluation (max 500) |
| `items[].file_id` | int | Oui | ID du fichier (entier positif) |
| `items[].rating` | int | Oui | Valeur d'évaluation (0–5) |

### Réponse

```json
{
  "total": 2,
  "succeeded": 2,
  "failed": 0,
  "errors": []
}
```

## GET /api/ratings/get

Obtenir l'évaluation d'un fichier. Retourne `rating: 0` si le fichier n'est pas évalué.

### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `file_id` | int | Oui | ID du fichier (paramètre de requête) |

### Réponse

```json
{
  "file_id": 42,
  "rating": 5
}
```

> **Note** : Les fichiers non évalués retournent `rating: 0`.

## POST /api/ratings/batch

Récupérer les évaluations pour plusieurs fichiers à la fois.

### Requête

```json
{
  "file_ids": [1, 2, 3]
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `file_ids` | array | Oui | Liste des ID de fichiers |

### Réponse

```json
{
  "ratings": {
    "1": 5,
    "3": 4
  }
}
```

> **Note** : Seuls les fichiers évalués apparaissent dans la carte. Les fichiers non évalués sont omis de la réponse.

## GET /api/ratings/stats

Obtenir les statistiques d'évaluation pour tous les fichiers.

### Paramètres

Aucun.

### Réponse

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

| Champ | Type | Description |
|-------|------|-------------|
| `total_rated` | int | Nombre total de fichiers évalués |
| `distribution` | object | Nombre de fichiers par valeur d'évaluation (1–5) |
