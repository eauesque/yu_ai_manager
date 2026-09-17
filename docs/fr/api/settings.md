# API Paramètres

API pour gérer les paramètres de l'application, le chiffrement des secrets et l'intégration du gestionnaire de mots de passe externes (1Password / Bitwarden).

Les valeurs secrètes sont toujours masquées (`****`) dans les réponses GET. Le champ `source` indique quel backend la valeur a été résolue.

## Authentification

Tous les points d'accès nécessitent l'authentification PIN ou l'authentification par clé API.

---

## GET /api/settings/schema

Récupérer la définition du schéma des paramètres complets. Retourne les noms de clés, les types, les valeurs par défaut, les catégories et d'autres métadonnées pour tous les paramètres.

### Paramètres

Aucun

### Réponse

```json
{
  "schema": [
    {
      "key": "pin",
      "type": "str",
      "default": "",
      "category": "security",
      "secret": true,
      "label": "PIN Code"
    }
  ]
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `key` | string | Clé de paramètre (séparée par des points, par ex. `github.token`) |
| `type` | string | Type de valeur (`str`, `int`, `float`, `bool`) |
| `default` | any | Valeur par défaut |
| `category` | string | Nom de la catégorie |
| `secret` | bool | Si c'est une valeur secrète |
| `label` | string | Étiquette d'affichage |

---

## GET /api/settings/all

Récupérer toutes les valeurs des paramètres. Les valeurs secrètes sont retournées de manière masquée.

### Paramètres

Aucun

### Réponse

```json
{
  "settings": [
    {
      "key": "pin",
      "value": "****",
      "source": "encrypted",
      "secret": true,
      "category": "security"
    },
    {
      "key": "theme",
      "value": "dark",
      "source": "config",
      "secret": false,
      "category": "appearance"
    }
  ]
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `key` | string | Clé de paramètre |
| `value` | any | Valeur actuelle (masquée si secrète) |
| `source` | string | Source de valeur : `default` / `config` / `encrypted` / `1password` / `bitwarden` |
| `secret` | bool | Si c'est une valeur secrète |
| `category` | string | Nom de la catégorie |

---

## GET /api/settings/\<key\>

Récupérer une valeur de paramètre unique. La clé utilise le format de chemin séparé par des points (par ex. `github.token`).

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `key` | string | Clé de paramètre (paramètre de chemin) |

### Réponse

```json
{
  "key": "github.token",
  "value": "****",
  "source": "1password",
  "secret": true,
  "category": "integrations"
}
```

### Erreurs

| Statut | Code | Description |
|--------|------|-------------|
| 404 | `not_found` | Clé de paramètre inconnue |

---

## PUT /api/settings/\<key\>

Mettre à jour une valeur de paramètre. Les valeurs secrètes sont automatiquement chiffrées. Spécifiez optionnellement un URI 1Password pour gérer le secret en externe.

### Limitation de débit

DESTRUCTIVE

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `key` | string | Clé de paramètre (paramètre de chemin) |

### Requête

```json
{
  "value": "new-value",
  "op_uri": "op://vault/item/field"
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `value` | any | Oui | La valeur à définir. Coercée automatiquement au type défini dans le schéma |
| `op_uri` | string | Non | URI 1Password. Quand spécifié, enregistre un mappage `op_secrets` au lieu de la valeur |

### Réponse

```json
{
  "key": "github.token",
  "updated": true
}
```

### Erreurs

| Statut | Code | Description |
|--------|------|-------------|
| 400 | `bad_request` | Corps de requête manquant `value` |
| 404 | `not_found` | Clé de paramètre inconnue |

---

## GET /api/settings/secrets/status

Récupérer le statut du backend de clé de chiffrement. Affiche la méthode de gestion de clé actuellement utilisée.

### Paramètres

Aucun

### Réponse

```json
{
  "backend": "keychain",
  "available": true,
  "keychain_supported": true
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `backend` | string | Backend de clé actuel (`keychain` / `passphrase` / `file`) |
| `available` | bool | Si le chiffrement est disponible |
| `keychain_supported` | bool | Si le keychain OS est supporté |

---

## POST /api/settings/secrets/export

Exporter la clé de chiffrement en tant que JSON protégé par mot de passe. Utilisé pour la sauvegarde ou la migration vers un autre environnement.

### Limitation de débit

DESTRUCTIVE

### Requête

```json
{
  "password": "my-export-password"
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `password` | string | Oui | Mot de passe pour protéger les données exportées |

### Réponse

```json
{
  "success": true,
  "export_data": "base64-encoded-encrypted-key-data"
}
```

### Erreurs

| Statut | Code | Description |
|--------|------|-------------|
| 400 | `bad_request` | Corps de requête manquant `password` |
| 400 | `export_failed` | Échec de l'opération d'export |

---

## POST /api/settings/secrets/import

Importer une clé de chiffrement à partir de données précédemment exportées.

### Limitation de débit

DESTRUCTIVE

### Requête

```json
{
  "export_data": "base64-encoded-encrypted-key-data",
  "password": "my-export-password"
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `export_data` | string | Oui | Les données obtenues lors de l'export |
| `password` | string | Oui | Le mot de passe défini lors de l'export |

### Réponse

```json
{
  "success": true,
  "message": "Key imported successfully"
}
```

### Erreurs

| Statut | Code | Description |
|--------|------|-------------|
| 400 | `bad_request` | Manque `export_data` ou `password` |
| 400 | `import_failed` | Mauvais mot de passe ou données corrompues |

---

## POST /api/settings/secrets/migrate-keychain

Migrer la clé de chiffrement du backend fichier vers le keychain OS. Supporte macOS Keychain, Windows Credential Manager et Linux Secret Service.

### Limitation de débit

DESTRUCTIVE

### Requête

Aucune (pas de corps requis)

### Réponse

```json
{
  "success": true,
  "message": "Key migrated to OS keychain"
}
```

### Erreurs

| Statut | Code | Description |
|--------|------|-------------|
| 400 | `migration_failed` | Keychain indisponible ou échec de la migration |

---

## GET /api/settings/op-status

Récupérer le statut de connexion 1Password CLI (`op`).

### Paramètres

Aucun

### Réponse

```json
{
  "available": true,
  "signed_in": true,
  "version": "2.24.0"
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `available` | bool | Si la commande `op` existe dans PATH |
| `signed_in` | bool | Si connecté à 1Password |
| `version` | string | Version CLI `op` |

---

## GET /api/settings/secrets/op-vaults

Lister les coffres 1Password disponibles.

### Paramètres

Aucun

### Réponse

```json
{
  "vaults": [
    {
      "id": "abc123",
      "name": "Personal"
    }
  ]
}
```

### Erreurs

| Statut | Code | Description |
|--------|------|-------------|
| 503 | `op_unavailable` | CLI 1Password non disponible |

---

## POST /api/settings/secrets/push-to-op

Écriture par lot de tous les paramètres secrets vers 1Password et enregistrement des mappages `op_secrets` dans config.json.

### Limitation de débit

DESTRUCTIVE

### Requête

```json
{
  "vault": "Personal",
  "item_title": "YU AI Manager",
  "remove_local": false
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `vault` | string | Oui | Nom du coffre 1Password cible |
| `item_title` | string | Non | Titre d'élément 1Password. Par défaut : `YU AI Manager` |
| `remove_local` | bool | Non | Si `true`, supprime les valeurs chiffrées localement de config.json après le push. Par défaut : `false` |

### Réponse

```json
{
  "message": "2 secrets pushed to 1Password",
  "pushed_keys": ["github.token", "pin"],
  "uris": {
    "github.token": "op://Personal/YU AI Manager/github.token",
    "pin": "op://Personal/YU AI Manager/pin"
  },
  "remove_local": false
}
```

### Erreurs

| Statut | Code | Description |
|--------|------|-------------|
| 400 | `bad_request` | Manque `vault` |
| 400 | `no_secrets` | Pas de secrets à envoyer |
| 500 | `op_push_failed` | Échec de l'écriture vers 1Password |
| 503 | `op_unavailable` | CLI 1Password non disponible |

---

## DELETE /api/settings/op-mapping/\<key\>

Supprimer un mappage URI 1Password, en revenant au chiffrement local.

### Limitation de débit

WRITE

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `key` | string | Clé de paramètre (paramètre de chemin) |

### Réponse

```json
{
  "key": "github.token",
  "unlinked": true
}
```

### Erreurs

| Statut | Code | Description |
|--------|------|-------------|
| 404 | `not_found` | Clé non trouvée dans le mappage `op_secrets` |

---

## GET /api/settings/bw-status

Récupérer le statut de connexion Bitwarden CLI (`bw`).

### Paramètres

Aucun

### Réponse

```json
{
  "available": true,
  "status": "unlocked"
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `available` | bool | Si la commande `bw` existe dans PATH |
| `status` | string | Statut de session Bitwarden |

---

## GET /api/settings/secrets/bw-folders

Lister les dossiers Bitwarden disponibles.

### Paramètres

Aucun

### Réponse

```json
{
  "folders": [
    {
      "id": "folder-uuid",
      "name": "Development"
    }
  ]
}
```

### Erreurs

| Statut | Code | Description |
|--------|------|-------------|
| 503 | `bw_unavailable` | CLI Bitwarden non disponible |

---

## POST /api/settings/secrets/push-to-bw

Écriture par lot de tous les paramètres secrets vers Bitwarden et enregistrement des mappages `bw_secrets` dans config.json.

### Limitation de débit

WRITE

### Requête

```json
{
  "folder_id": "folder-uuid",
  "item_name": "YU AI Manager"
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `folder_id` | string/null | Non | ID du dossier Bitwarden cible. Omettez pour aucun dossier |
| `item_name` | string | Non | Nom d'élément Bitwarden. Par défaut : `YU AI Manager` |

### Réponse

```json
{
  "message": "2 secrets pushed to Bitwarden",
  "pushed_keys": ["github.token", "pin"],
  "mappings": {
    "github.token": {"item_id": "item-uuid", "field": "github.token"},
    "pin": {"item_id": "item-uuid", "field": "pin"}
  }
}
```

### Erreurs

| Statut | Code | Description |
|--------|------|-------------|
| 400 | `no_secrets` | Pas de secrets à envoyer |
| 500 | `bw_push_failed` | Échec de l'écriture vers Bitwarden |
| 503 | `bw_unavailable` | CLI Bitwarden non disponible |

---

## DELETE /api/settings/bw-mapping/\<key\>

Supprimer un mappage Bitwarden, en revenant au chiffrement local.

### Limitation de débit

WRITE

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `key` | string | Clé de paramètre (paramètre de chemin) |

### Réponse

```json
{
  "key": "github.token",
  "unlinked": true
}
```

### Erreurs

| Statut | Code | Description |
|--------|------|-------------|
| 404 | `not_found` | Clé non trouvée dans le mappage `bw_secrets` |
