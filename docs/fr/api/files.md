# API Fichiers

API pour récupérer les détails des fichiers, les miniatures et les médias originaux.

## GET /api/file/<id>

Récupérer les métadonnées détaillées d'un fichier.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `id` | int | ID du fichier (paramètre de chemin) |

### Réponse

```json
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
  "positive": "1girl, landscape",
  "negative": "low quality",
  "steps": 28,
  "sampler": "Euler a",
  "cfg_scale": 7.0,
  "seed": 1234567890,
  "rating": 4,
  "is_favorite": true,
  "tags": ["landscape"],
  "collections": [1, 3],
  "hash_md5": "abc123...",
  "hash_phash": "def456...",
  "analysis": { "description": "A scenic landscape..." }
}
```

## GET /api/thumbnail/<id>

Image miniature (WebP). Supporte la mise en cache ETag.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `id` | int | ID du fichier |
| `size` | int | Taille de la miniature (par défaut 300) |

### Réponse

- Content-Type: `image/webp`
- Support ETag / If-None-Match (304 Not Modified)
- Cache : 24 heures

## GET /api/original/<id>

Diffuser le fichier original. Supporte également les fichiers à l'intérieur des archives ZIP.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `id` | int | ID du fichier |

### Réponse

- Content-Type: Type MIME du fichier
- Content-Disposition: `inline`
- Support des demandes Range (pour la recherche vidéo)

## POST /api/convert

Conversion de format de prompt (A1111 <-> NAI).

### Requête

```json
{
  "prompt": "1girl, (masterpiece:1.2)",
  "direction": "a1111_to_nai"
}
```

### Réponse

```json
{
  "converted": "1girl, {{masterpiece}}",
  "direction": "a1111_to_nai"
}
```

## GET /api/container-thumb-ids

Liste des ID de miniatures pour un conteneur (dossier/ZIP), excluant les entrées déjà en cache.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `keys` | string | Clés de conteneur (séparées par des virgules) |
