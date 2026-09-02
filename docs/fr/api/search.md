# API Recherche

API pour la recherche de fichiers, les suggestions et l'affichage groupé.

## GET /api/search

Le point d'accès principal de recherche de fichiers.

### Paramètres

| Paramètre | Type | Par défaut | Description |
|-----------|------|-----------|-------------|
| `q` | string | `""` | Requête de recherche (texte dans les prompts, noms d'étiquette) |
| `sort` | string | `"date"` | Ordre de tri : `date`, `name`, `size`, `rating`, `random` |
| `order` | string | `"desc"` | `asc` / `desc` |
| `offset` | int | `0` | Position de démarrage de la pagination |
| `limit` | int | `50` | Nombre de résultats (max 200) |
| `cursor` | string | - | Token pour pagination basée sur le curseur |
| `meta` | string | `"all"` | Type de métadonnées : `all`, `a1111`, `nai`, `comfy`, `unknown` |
| `tags` | string | - | Filtre d'étiquette (séparées par des virgules) |
| `rating_min` | int | - | Évaluation minimale (0-5) |
| `rating_max` | int | - | Évaluation maximale (0-5) |
| `path` | string | - | Filtre préfixe du chemin |
| `ext` | string | - | Filtre d'extension (séparées par des virgules, par ex. `png,webp`) |
| `has_prompt` | bool | - | Filtrer par présence de prompt |
| `collection_id` | int | - | Rechercher dans une collection |
| `favorites_only` | bool | `false` | Favoris uniquement |
| `group_by` | string | - | Regroupement : `folder`, `conversation` |

### Réponse

```json
{
  "results": [
    {
      "id": 42,
      "path": "/images/output/00042.png",
      "filename": "00042.png",
      "size": 1234567,
      "mtime": 1709500000,
      "width": 1024,
      "height": 1536,
      "meta_type": "a1111_png",
      "model_name": "animagine-xl-3.1",
      "positive": "1girl, landscape, sunset",
      "negative": "low quality",
      "rating": 4,
      "is_favorite": true,
      "tags": ["landscape", "sunset"]
    }
  ],
  "total": 1500,
  "offset": 0,
  "limit": 50,
  "next_cursor": "eyJtdGltZSI6MTcwOTUwMDAwMCwiaWQiOjQyfQ=="
}
```

## GET /api/search-grouped

Résultats de recherche groupés par dossier/ZIP.

### Paramètres

Les mêmes paramètres de requête que `/api/search`, plus :

| Paramètre | Type | Description |
|-----------|------|-------------|
| `group_limit` | int | Nombre maximum d'éléments affichés par groupe |

## GET /api/groups-index

Index des groupes de dossier et conteneur ZIP. Utilisé pour le regroupement des résultats de recherche.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `sort` | string | Ordre de tri : `name`, `count`, `date` |
| `order` | string | `asc` / `desc` |
| `offset` | int | Position de démarrage de la pagination |
| `limit` | int | Nombre de résultats |

## GET /api/group-members

Liste des ID de fichiers dans un conteneur spécifié.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `key` | string | Clé du conteneur (chemin de dossier ou chemin ZIP) |

## GET /api/suggest

Autocomplétion pour les étiquettes et les prompts.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `q` | string | Texte d'entrée |
| `limit` | int | Nombre de suggestions (par défaut 10) |

### Réponse

```json
{
  "suggestions": [
    { "value": "1girl", "count": 5432 },
    { "value": "1boy", "count": 1234 }
  ]
}
```

## GET /api/suggest/lora

Suggestions de noms de modèles LoRA.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `q` | string | Texte d'entrée |
| `limit` | int | Nombre de suggestions |

## GET /api/server-info

Informations de base du serveur.

### Réponse

```json
{
  "version": "4.12.1",
  "db_path": "/path/to/tags.db",
  "file_count": 150000,
  "tag_count": 8500,
  "auth_required": false,
  "lan_ip": "192.168.1.100",
  "active_ui": "default"
}
```
