# API Favoris

API pour ajouter, supprimer, vérifier et lister les favoris.

## POST /api/favorites/toggle

Basculer le statut de favori d'un fichier. Ajoute le fichier s'il n'est pas déjà en favori ; l'supprime s'il est déjà présent.

- **Limitation de débit** : WRITE

### Corps de la requête

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `file_id` | int | Oui | ID du fichier cible (entier positif) |
| `collection_id` | int | Non | ID de collection (par défaut : 1) |

```json
{
  "file_id": 42,
  "collection_id": 1
}
```

### Réponse

```json
{
  "file_id": 42,
  "collection_id": 1,
  "favorited": true
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `file_id` | int | ID du fichier cible |
| `collection_id` | int | ID de collection |
| `favorited` | bool | État après basculement. `true` = ajouté, `false` = supprimé |

## GET /api/favorites/check

Retourne lesquels des ID de fichiers spécifiés sont en favoris.

### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `ids` | string | Oui | ID de fichiers séparés par des virgules (par ex. `1,2,3`) |
| `collection_id` | int | Non | Filtrer vers une collection spécifique |

### Réponse

```json
{
  "favorites": [1, 3]
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `favorites` | int[] | Tableau des ID de fichiers en favoris |

## GET /api/favorites/check_collections

Retourne les ID de collections qui contiennent le fichier spécifié.

### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `file_id` | int | Oui | ID du fichier cible |

### Réponse

```json
{
  "collections": [1, 3]
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `collections` | int[] | Tableau des ID de collections contenant ce fichier |

## GET /api/favorites/list

Récupère une liste d'ID de fichiers en favoris. Les résultats sont triés par date d'ajout en ordre décroissant. Les fichiers supprimés logiquement sont exclus.

### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `collection_id` | int | Non | Filtrer vers une collection spécifique |

### Réponse

```json
{
  "ids": [42, 55, 67]
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `ids` | int[] | Tableau d'ID de fichiers en favoris (ordonné par `added_at` DESC) |
