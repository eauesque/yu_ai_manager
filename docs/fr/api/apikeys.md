# API des clés API

API pour créer, lister et supprimer des clés API. Tous les points d'accès nécessitent l'authentification par session PIN.

Les clés API sont générées au format `sk_` + 32 caractères hexadécimaux (128 bits). Seul le hachage est stocké côté serveur ; la clé brute est retournée une seule fois au moment de la création.

## Scopes

Les clés API peuvent se voir assigner des scopes pour restreindre les points d'accès auxquels elles peuvent accéder. Les clés sans scopes ont par défaut un accès en lecture seule.

| Scope | Description |
|-------|-------------|
| `read` | Recherche, détails des fichiers, miniatures, statistiques |
| `rate` | Évaluation obtenir/définir/lot |
| `tag.write` | Ajouter/supprimer une étiquette |
| `collection.write` | Collection créer/mettre à jour/supprimer, ajouter par lot, favoris |
| `annotate` | Annotation lire/écrire/supprimer |
| `scan` | Analyse démarrer/annuler/reprendre |
| `admin` | Gestion des clés API, paramètres, sauvegarde/restauration |

## POST /api/apikeys

Créer une nouvelle clé API.

### Limitation de débit

WRITE (scope: `admin`)

### Authentification

Session PIN ou clé API avec scope `admin`

### Requête

```json
{
  "label": "My Integration",
  "scopes": ["read", "rate"]
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `label` | string | Non | Étiquette d'identification pour la clé. Par défaut `Key <timestamp>` si omis |
| `scopes` | string[] | Non | Tableau des scopes. Omettez ou passez un tableau vide pour un accès en lecture seule |

### Réponse (201)

```json
{
  "id": "ak_1a2b3c4d5e6f7890",
  "key": "sk_abcdef1234567890abcdef1234567890",
  "key_prefix": "sk_abcdef12",
  "label": "My Integration",
  "created_at": 1709500000,
  "scopes": ["read", "rate"]
}
```

> **Note** : Le champ `key` est inclus uniquement dans la réponse de création. Cette valeur ne peut pas être récupérée à nouveau, donc stockez-la dans un endroit sécurisé.

### Erreurs

| Statut | Description |
|--------|-------------|
| 400 | Scope invalide spécifié |

## GET /api/apikeys

Lister toutes les clés API. Les hachages ne sont pas inclus ; seul le préfixe est retourné.

### Authentification

Session PIN ou clé API avec scope `admin`

### Paramètres

Aucun

### Réponse

```json
{
  "keys": [
    {
      "id": "ak_1a2b3c4d5e6f7890",
      "key_prefix": "sk_abcdef12",
      "label": "My Integration",
      "created_at": 1709500000,
      "last_used_at": 1709600000,
      "scopes": ["read", "rate"]
    }
  ]
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `id` | string | ID de la clé (préfixe `ak_`) |
| `key_prefix` | string | Premiers 10 caractères de la clé (pour identification) |
| `label` | string | Étiquette définie par l'utilisateur |
| `created_at` | int | Heure de création (timestamp Unix) |
| `last_used_at` | int/null | Heure de dernier usage. `null` si jamais utilisé |
| `scopes` | string[] | Scopes assignés. Le champ est omis si aucun scope n'est défini |

## DELETE /api/apikeys/<key_id>

Supprimer (révoquer) une clé API.

### Limitation de débit

WRITE (scope: `admin`)

### Authentification

Session PIN ou clé API avec scope `admin`

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `key_id` | string | ID de la clé API (paramètre de chemin) |

### Réponse

```json
{
  "deleted": "ak_1a2b3c4d5e6f7890"
}
```

### Erreurs

| Statut | Description |
|--------|-------------|
| 404 | Clé avec l'ID spécifié non trouvée |

## Utiliser les clés API

Utilisez la clé API créée via l'en-tête `Authorization` :

```
Authorization: Bearer sk_abcdef1234567890abcdef1234567890
```

Les requêtes authentifiées avec des clés API ne nécessitent pas l'en-tête CSRF (`X-Requested-With`).
