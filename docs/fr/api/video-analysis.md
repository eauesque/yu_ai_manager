# API d'analyse vidéo

API pour gérer la configuration de l'analyse vidéo et vérifier le statut. Contrôle les paramètres pour extraire les keyframes des fichiers vidéo.

## GET /api/video-analysis/config

Obtenir la configuration actuelle de l'analyse vidéo. Retourne les paramètres enregistrés fusionnés avec les valeurs par défaut.

### Paramètres

Aucun

### Réponse

```json
{
  "config": {
    "enabled": true,
    "keyframe_count": 4,
    "strategy": "uniform",
    "scene_threshold": 0.4,
    "store_per_keyframe": false
  }
}
```

| Champ | Type | Par défaut | Description |
|-------|------|-----------|-------------|
| `enabled` | boolean | `true` | Si l'analyse vidéo est activée |
| `keyframe_count` | int | `4` | Nombre de keyframes à extraire (1-16) |
| `strategy` | string | `"uniform"` | Stratégie d'extraction de keyframe. `uniform` (espacés uniformément), `scene` (détection de changement de scène), `single` (seule une trame) |
| `scene_threshold` | float | `0.4` | Seuil de détection de changement de scène (0.0-1.0). Utilisé quand `strategy` est `scene` |
| `store_per_keyframe` | boolean | `false` | Si chaque keyframe doit être stocké individuellement |

## POST /api/video-analysis/config

Enregistrer la configuration de l'analyse vidéo. Seuls les champs spécifiés sont mis à jour ; les champs omis conservent leurs valeurs existantes.

### Limitation de débit

WRITE

### Requête

```json
{
  "enabled": true,
  "keyframe_count": 8,
  "strategy": "scene",
  "scene_threshold": 0.3,
  "store_per_keyframe": false
}
```

Tous les champs sont optionnels. Seuls les champs spécifiés sont mis à jour.

| Paramètre | Type | Requis | Contraintes | Description |
|-----------|------|--------|-------------|-------------|
| `enabled` | boolean | Non | - | Si l'analyse vidéo est activée |
| `keyframe_count` | int | Non | 1-16 | Nombre de keyframes à extraire |
| `strategy` | string | Non | `uniform`, `scene` ou `single` | Stratégie d'extraction de keyframe |
| `scene_threshold` | float | Non | 0.0-1.0 | Seuil de détection de changement de scène |
| `store_per_keyframe` | boolean | Non | - | Si chaque keyframe doit être stocké individuellement |

### Réponse

Retourne la configuration fusionnée après l'enregistrement (même format que GET).

```json
{
  "config": {
    "enabled": true,
    "keyframe_count": 8,
    "strategy": "scene",
    "scene_threshold": 0.3,
    "store_per_keyframe": false
  }
}
```

### Erreurs

| Statut | Code | Condition |
|--------|------|-----------|
| 400 | `invalid_json` | Le corps de la requête n'est pas un objet JSON |
| 400 | `invalid_value` | Erreur de validation (type incorrect, valeur hors plage, stratégie invalide, etc.) |

## GET /api/video-analysis/status

Obtenir les informations de statut de l'analyse vidéo. Retourne la disponibilité de ffmpeg, le nombre de fichiers vidéo et le nombre de fichiers avec des keyframes extraites.

### Paramètres

Aucun

### Réponse

```json
{
  "ffmpeg": true,
  "video_files": 150,
  "files_with_keyframes": 42
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `ffmpeg` | boolean | Si ffmpeg est disponible sur le système |
| `video_files` | int | Nombre total de fichiers vidéo dans la base de données (excluant suppression logique). Extensions supportées : `.mp4`, `.webm`, `.avi`, `.mov`, `.mkv`, `.m4v`, `.ogv` |
| `files_with_keyframes` | int | Nombre de fichiers qui ont des keyframes extraites |
