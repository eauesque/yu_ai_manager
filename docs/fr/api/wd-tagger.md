# API WD Tagger

APIs for WD Tagger (Waifu Diffusion Tagger) Danbooru auto-tagging. Provides config management, single/batch tagging, tag CRUD, modèle management, XMP reading, and VLM connection testing.

## GET /api/wd-tagger/config

Obtenir le WD Tagger configuration.

### Paramètres

None

### Réponse

```json
{
  "config": {
    "model": "SmilingWolf/wd-swinv2-tagger-v3",
    "threshold": 0.35,
    "...": "..."
  }
}
```

## POST /api/wd-tagger/config

Save/update WD Tagger configuration.

### Rate Limit

WRITE

### Requête

```json
{
  "model": "SmilingWolf/wd-swinv2-tagger-v3",
  "threshold": 0.35
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| *(any key)* | any | No | Configuration field. Unknown keys or invalid values return `400` |

### Réponse

```json
{
  "config": {
    "model": "SmilingWolf/wd-swinv2-tagger-v3",
    "threshold": 0.35,
    "...": "..."
  }
}
```

### Erreurs

| Code | Status | Description |
|------|--------|-------------|
| `invalid_json` | 400 | Requête body is not a JSON object |
| `invalid_value` | 400 | Invalid configuration value |

## POST /api/wd-tagger/tag/<file_id>

Run WD Tagger inference on a single file to predict and assign Danbooru tags.

### Rate Limit

HEAVY

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `file_id` | int | File ID (path parameter) |

### Requête

```json
{
  "force": false
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `force` | boolean | No | If `true`, overwrite existing tags and re-run inference. Défaut `false` |

### Réponse

```json
{
  "file_id": 42,
  "model": "SmilingWolf/wd-swinv2-tagger-v3",
  "tags": [
    {"tag": "1girl", "score": 0.98, "category": "general"},
    {"tag": "solo", "score": 0.95, "category": "general"}
  ]
}
```

### Erreurs

| Code | Status | Description |
|------|--------|-------------|
| `tag_error` | 400 | Tagging failed (file not found, image load error, etc.) |

## GET /api/wd-tagger/tags/<file_id>

Get stored WD Tagger tags for a specific file.

### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | File ID (path parameter) |
| `modèle` | string | No | Filter by modèle name (query parameter) |

### Réponse

```json
{
  "file_id": 42,
  "tags": [
    {"tag": "1girl", "score": 0.98, "category": "general", "model": "SmilingWolf/wd-swinv2-tagger-v3"},
    {"tag": "solo", "score": 0.95, "category": "general", "model": "SmilingWolf/wd-swinv2-tagger-v3"}
  ]
}
```

## DELETE /api/wd-tagger/tags/<file_id>

Delete WD Tagger tags for a specific file.

### Rate Limit

WRITE

### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | File ID (path parameter) |
| `modèle` | string | No | Filter by modèle name (query parameter). If omitted, deletes tags from all modèles |

### Réponse

```json
{
  "file_id": 42,
  "deleted": 15
}
```

## DELETE /api/wd-tagger/tags/batch

Delete WD Tagger tags for multiple files at once.

### Rate Limit

WRITE

### Requête

```json
{
  "file_ids": [1, 2, 3],
  "model": "wd-swinv2-tagger-v3"
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `file_ids` | list | Yes | Tableau of file IDs (max 500) |
| `modèle` | string | No | Filter by modèle name. If omitted, deletes tags from all modèles |

### Réponse

```json
{
  "deleted_files": 3,
  "deleted_tags": 45
}
```

## Active model (v4.192.0+)

Lorsqu'un même fichier est réétiqueté avec plusieurs modèles WD Tagger,
`file_wd_tags` conserve les tags de chaque modèle comme historique. Avec un
active model, l'affichage de détail, la recherche `ai_analyzed` et le test
interne "déjà tagué" de WD Tagger n'utilisent que les tags de ce modèle. Si aucun
active model n'est défini, le comportement précédent est conservé et les tags de
tous les modèles sont utilisés ensemble.

### Configuration dans l'UI

Le retag modal affiche le `Active model` courant en haut. Le dropdown `Change`
permet de choisir un modèle disponible. Choisir `(none / reset)` efface l'active
model.

Après un retag, le modèle utilisé devient actif par défaut. Désactivez la case
"Définir comme modèle actif après réétiquetage" dans le retag modal pour garder
l'active model actuel.

Les rows des anciens modèles ne sont pas supprimées automatiquement. Elles
restent en base comme historique. Pour les supprimer explicitement, activez
"Supprimer aussi les tags des autres modèles" dans le retag modal et confirmez
le dialogue après le retag.


### GET /api/wd-tagger/profiles

Returns registered WD Tagger profiles and the current active model. Requires admin scope.

```json
{
  "profiles": [
    {
      "id": "camie_tagger_v2",
      "display_name": "Camie Tagger v2",
      "model_id": "Camais03/camie-tagger-v2",
      "adapter_family": "camie",
      "backend": "onnx",
      "builtin": true,
      "has_tags": false
    }
  ],
  "active_model_id": "Camais03/camie-tagger-v2"
}
```

### GET /api/wd-tagger/active-model

Retourne l'active model courant et la liste des modèles présents en base.
Admin scope requis.

```json
{
  "active_model_id": "SmilingWolf/wd-eva02-large-tagger-v3",
  "available_models": [
    {"model_id": "SmilingWolf/wd-eva02-large-tagger-v3", "file_count": 120},
    {"model_id": "SmilingWolf/wd-swinv2-tagger-v3", "file_count": 340}
  ]
}
```

### PUT /api/wd-tagger/active-model

Change l'active model. Admin scope requis. Envoyez `null` ou une chaîne vide
comme `model_id` pour réinitialiser.

```json
{
  "model_id": "SmilingWolf/wd-eva02-large-tagger-v3"
}
```

| Code | Statut | Description |
|------|--------|-------------|
| `invalid_model_id` | 400 | model_id est trop long ou contient des caractères de contrôle |
| `unknown_model` | 400 | Aucun tag du modèle indiqué n'existe en base |

## POST /api/wd-tagger/batch

Run batch tagging on multiple files. If `file_ids` is specified, only those files are processed. If omitted, automatically selects untagged files up to `limit`.

### Rate Limit

HEAVY

### Requête

```json
{
  "file_ids": [1, 2, 3],
  "limit": 100,
  "force": false,
  "scan_root": ""
}
```

| Paramètre | Type | Requis | Limit | Description |
|-----------|------|----------|-------|-------------|
| `file_ids` | int[] | No | Max 500 | Tableau of target file IDs. If omitted, untagged files are selected automatically |
| `limit` | int | No | - | Max files to process when `file_ids` is omitted. Défaut `100` |
| `force` | boolean | No | - | If `true`, overwrite existing tags. Défaut `false` |
| `scan_root` | string | No | - | Filter by scan root path. Empty string for all files |

### Réponse

```json
{
  "job_id": "wd_tagger",
  "total": 100,
  "status": "started"
}
```

### Erreurs

| Code | Status | Description |
|------|--------|-------------|
| `batch_too_large` | 400 | `file_ids` exceeds 500 items |
| `batch_error` | 409 | A batch job is already running |

## POST /api/wd-tagger/batch/cancel

Cancel a running batch tagging job.

### Rate Limit

WRITE

### Requête

No body required.

### Réponse

```json
{
  "status": "cancelling",
  "message": "Batch tagging cancel requested"
}
```

### Erreurs

| Code | Status | Description |
|------|--------|-------------|
| `job_not_running` | 404 | No running batch tagging job exists |

## GET /api/wd-tagger/stats

Get WD Tagger tagging statistics.

### Paramètres

None

### Réponse

```json
{
  "total_tagged": 1234,
  "total_tags": 56789,
  "models": {
    "SmilingWolf/wd-swinv2-tagger-v3": 1200
  },
  "untagged_unknown": 42
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `total_tagged` | int | Number of tagged files |
| `total_tags` | int | Total number of stored tags |
| `modèles` | object | Number of tagged files per modèle |
| `untagged_unknown` | int | Number of files with no metadata (`unknown`) and no WD tags |

## GET /api/wd-tagger/untagged

List files with no metadata (`unknown`) that have not been tagged yet. Supports pagination.

### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `limit` | int | No | Nombre de résultats. 1-500, default `100` |
| `offset` | int | No | Nombre de résultats to skip. Défaut `0` |

### Réponse

```json
{
  "files": [
    {"id": 10, "filepath": "/images/photo.png", "filename": "photo.png"}
  ],
  "total": 42
}
```

## GET /api/wd-tagger/xmp/<file_id>

Read XMP metadata from a specific file.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `file_id` | int | File ID (path parameter) |

### Réponse

```json
{
  "file_id": 42,
  "xmp": {
    "subject": ["1girl", "solo", "blue_eyes"],
    "description": "...",
    "creator": "..."
  }
}
```

### Erreurs

| Code | Status | Description |
|------|--------|-------------|
| `file_not_found` | 404 | File does not exist or is soft-deleted |

## GET /api/wd-tagger/vlm/test

Test connectivity to a VLM (Vision Language Model) serveur. Checks reachability of an OpenAI-compatible API endpoint.

### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `url` | string | Yes | VLM serveur URL (query parameter) |

### Réponse

```json
{
  "ok": true,
  "message": "Connection successful",
  "server_info": "..."
}
```

### Erreurs

| Code | Status | Description |
|------|--------|-------------|
| `missing_url` | 400 | `url` parameter not provided |
| `invalid_url` | 400 | URL format is invalid |

## GET /api/wd-tagger/vlm/modèles

List available modèles on a VLM serveur. Queries the OpenAI-compatible `/v1/modèles` endpoint.

### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `url` | string | Yes | VLM serveur URL (query parameter) |

### Réponse

```json
{
  "models": [
    {"id": "llava-v1.6", "object": "model"}
  ]
}
```

### Erreurs

| Code | Status | Description |
|------|--------|-------------|
| `missing_url` | 400 | `url` parameter not provided |
| `invalid_url` | 400 | URL format is invalid |
| `vlm_connection_error` | 502 | Failed to connect to VLM serveur |

## POST /api/wd-tagger/modèle/download

Download a WD Tagger modèle. Fetches modèle files from Hugging Face and saves them locally.

### Rate Limit

HEAVY

### Requête

```json
{
  "repo": "SmilingWolf/wd-swinv2-tagger-v3"
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `repo` | string | No | Hugging Face repository name. If omitted, uses the `modèle` value from config |

### Réponse

```json
{
  "repo": "SmilingWolf/wd-swinv2-tagger-v3",
  "path": "/path/to/model/directory",
  "ready": true
}
```

### Erreurs

| Code | Status | Description |
|------|--------|-------------|
| `unknown_modèle` | 400 | Unknown modèle repository. `hint` contains list of known modèles |
| `download_failed` | 500 | Download failed |

## GET /api/wd-tagger/modèle/status

Check the download status of a WD Tagger modèle.

### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `repo` | string | No | Hugging Face repository name (query parameter). If omitted, uses the `modèle` value from config |

### Réponse

```json
{
  "repo": "SmilingWolf/wd-swinv2-tagger-v3",
  "downloaded": true,
  "path": "/path/to/model/directory",
  "known_models": {
    "SmilingWolf/wd-swinv2-tagger-v3": "SwinV2 (recommended)",
    "SmilingWolf/wd-convnext-tagger-v3": "ConvNeXt",
    "SmilingWolf/wd-vit-tagger-v3": "ViT"
  }
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `repo` | string | Repository name being checked |
| `downloaded` | boolean | Si the modèle is downloaded locally |
| `path` | string/null | Local modèle path if downloaded |
| `known_modèles` | object | All supported modèles (repository name -> display name) |

## User profile CRUD (v4.197.0+)

API pour faire le CRUD des tagger profiles créés par l’utilisateur depuis l’UI de la page Tools. Tous les endpoints nécessitent l’admin scope. Le format d’erreur commun est `{ok: false, error, code, ...extra}`. Le body de requête a un **hard cap de 1MB** (`code: profile_too_large`, 413). `id` doit respecter la regex `^[a-z0-9][a-z0-9_-]{0,63}$`.

### POST /api/wd-tagger/profiles

Créer un nouveau profile utilisateur.

**Requête**: profile JSON (schema v2, `profile_version: "2"`). Le champ `builtin` est forcé à `false` côté serveur.

**Réponse (200)**:
```json
{
  "ok": true,
  "profile": { "...": "...サニタイズ済 profile JSON..." },
  "origin": "user",
  "overrides_builtin": false
}
```

| Champ | Description |
|---|---|
| `profile` | Profile sauvegardé (garanti `builtin: false`) |
| `origin` | Toujours `"user"` |
| `overrides_builtin` | `true` si un profile builtin avec le même id existe (chemin avancé) |

**Erreurs**:

| status | code | condition |
|---|---|---|
| 400 | `validation_failed` | Le JSON viole le schema v2 (`extra.errors=[{path, message}, ...]`) |
| 400 | `invalid_id` | Le `id` dans le body ne respecte pas la regex |
| 409 | `id_conflict` | Même id qu’un profile utilisateur existant |
| 413 | `profile_too_large` | body > 1MB |

### GET /api/wd-tagger/profiles/{id}

Récupérer le profile schema v2 complet pour l’id spécifié (appelé par l’UI lors de l’édition / duplication / Export).

**path**: `id` (vérification regex requise)

**Réponse (200)**:
{Même format que POST: profile / origin / overrides_builtin}

**Erreurs**:
- 400 `invalid_id` (l’id du path ne respecte pas la regex)
- 404 `not_found`

### PUT /api/wd-tagger/profiles/{id}

Mettre à jour un profile utilisateur existant.

**path**: `id` (vérification regex requise)

**Requête**: profile JSON. `body.id` doit correspondre à l’id du path (pour renommer, guider l’UI vers `Duplicate → Delete`).

**Réponse (200)**: Même format que POST.

**Erreurs**:

| status | code | condition |
|---|---|---|
| 400 | `id_immutable` | l’id du path et l’id du body ne correspondent pas |
| 400 | `invalid_id` | l’id du path ne respecte pas la regex |
| 400 | `validation_failed` | violation du schema |
| 403 | `builtin_read_only` | l’id du path est un profile builtin (aucun fichier utilisateur correspondant) |
| 404 | `not_found` | id non enregistré |
| 413 | `profile_too_large` | body > 1MB |

### DELETE /api/wd-tagger/profiles/{id}

Supprimer un profile utilisateur.

**path**: `id`

**Réponse (200)**:
```json
{"ok": true, "deleted": true}
```

**Erreurs**:

| status | code | condition |
|---|---|---|
| 400 | `invalid_id` | id du path invalide |
| 403 | `builtin_read_only` | builtin uniquement, sans override utilisateur |
| 404 | `not_found` | id non enregistré |
| 409 | `in_use` | Ce profile est le modèle actif (inclut `extra.active_model_id`). Dans l’UI, bascule le profile actif via `PUT /api/wd-tagger/active-model` puis réessaie |

### POST /api/wd-tagger/profiles/{id}/test

dry-run download. Fait un HEAD pour chaque `files[]` sur HuggingFace et, pour ceux avec `required: true`, effectue un téléchargement atomique par fichier (le cache réutilise le chemin existant).

**path**: `id`

**body**: non requis

**Comportement**:
- per-file timeout: 30s
- timeout global: 60s
- redirect: allowlist uniquement pour les sous-domaines `huggingface.co` / `hf.co`, max 5 hops; userinfo (`user:pass@`) est SSRFBlocked

**Réponse (200, succès)**:
```json
{
  "ok": true,
  "files": [
    {"name": "model.onnx", "status": "downloaded", "size": 1234567},
    {"name": "tags.csv",   "status": "cached",     "size": 89012},
    {"name": "optional.json", "status": "skipped_optional", "size": null}
  ]
}
```

Valeurs de `status`:
- `downloaded`: téléchargé dans cette exécution
- `cached`: existe déjà localement (HEAD seulement)
- `skipped_optional`: `required: false` et 404 / HEAD a échoué

**Erreurs (status / code)**:

| status | code | condition |
|---|---|---|
| 400 | `invalid_id` / `required_missing` | id du path invalide / fichier required est 404 sur HF |
| 404 | `not_found` | profile non enregistré |
| 408 | `timeout` | dépassement du total 60s |
| 502 | `ssrf_blocked` | redirect hors allowlist HF / contient userinfo / scheme n’est pas http(s) |
| 502 | `hf_unavailable` | HF a renvoyé 5xx |

En cas d’erreur, le body est de la forme `{"ok": false, "code": ..., "error": ..., "files": [...résultats partiels...], "detail": "..."}`.

### Format profile JSON (schema v2)

```typescript
interface ProfileV2 {
  profile_version: "2";
  id: string;
  display_name: string;
  adapter_family: "wd" | "camie" | "oppai" | "generic_onnx";
  backend: "onnx";
  model_id: string;                        // Chemin du repo HF "<owner>/<name>"
  hf_subdir: string | null;
  files: { name: string; required: boolean; size_hint_mb?: number }[];
  default_thresholds: Record<string, number>;
  tag_source: TagSourceSpec;               // type=csv/json_list/json_dict/composite
  threshold_source: ThresholdSourceSpec;   // type=global_per_category/per_tag_json
  preprocess_spec: PreprocessSpec;
  supports_categories: string[];
  categories_mode: "from_tag_source" | "all_general";
  builtin?: boolean;                       // toujours false pour l’origine user (forcé par le serveur)
}
```

Pour plus de détails, voir `extensions/builtin_wd_tagger/core_impl/adapters/base.py` (`TaggerProfile`), ou l’implémentation de référence builtin (`extensions/builtin_wd_tagger/core_impl/profiles/*.json`).
