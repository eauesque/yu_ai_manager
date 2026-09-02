# API de gestion de l'interface

API pour lister, changer, installer et désinstaller les thèmes d'interface.

## GET /api/ui/list

Lister tous les interfaces installés. Retourne les informations du manifeste, le statut actif et si les fichiers de modèles/statiques existent pour chaque interface.

### Paramètres

Aucun

### Réponse

```json
{
  "data": {
    "uis": [
      {
        "name": "default",
        "active": true,
        "manifest": {
          "name": "Default UI",
          "version": "1.0.0",
          "description": "Built-in reference UI"
        },
        "has_templates": true,
        "has_static": true
      },
      {
        "name": "custom-dark",
        "active": false,
        "manifest": {
          "name": "Custom Dark",
          "version": "0.2.0",
          "description": "Dark theme variant"
        },
        "has_templates": true,
        "has_static": true
      }
    ]
  }
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `name` | string | Nom du répertoire de l'interface |
| `active` | boolean | Si c'est l'interface actuellement actif |
| `manifest` | object | Contenu de `manifest.json` |
| `has_templates` | boolean | Si un répertoire `templates/` existe |
| `has_static` | boolean | Si un répertoire `static/` existe |

## POST /api/ui/switch

Changer l'interface actif. Le changement est enregistré dans `config.json` et nécessite un redémarrage du serveur pour prendre effet.

### Limitation de débit

WRITE

### Requête

```json
{
  "name": "custom-dark"
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `name` | string | Oui | Nom de l'interface cible. Seuls les caractères alphanumériques, les tirets et les traits de soulignement sont autorisés |

### Réponse

```json
{
  "name": "custom-dark",
  "restart_required": true
}
```

### Erreurs

| Statut | Condition |
|--------|-----------|
| 400 | Le nom de l'interface est vide ou contient des caractères invalides |
| 404 | L'interface spécifiée n'existe pas |
| 400 | `manifest.json` est manquant ou invalide |
| 500 | Échec de l'enregistrement de `config.json` |

## POST /api/ui/install

Installer une interface à partir d'une URL. **Uniquement autorisé depuis localhost.**

### Limitation de débit

WRITE

### Authentification

Nécessite l'authentification PIN ou la clé API, plus la requête doit provenir de localhost. Les requêtes à distance sont rejetées avec 403.

### Requête

```json
{
  "url": "https://github.com/user/my-ui/archive/refs/heads/main.zip"
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `url` | string | Oui | URL du package de l'interface (archive zip, etc.) |

### Réponse

```json
{
  "name": "my-ui",
  "installed": true
}
```

### Erreurs

| Statut | Condition |
|--------|-----------|
| 400 | L'URL est vide |
| 403 | La requête ne provient pas de localhost |

## DELETE /api/ui/<name>/uninstall

Désinstaller une interface. **Uniquement autorisé depuis localhost.** L'interface par défaut (`default`) ne peut pas être supprimé.

Si l'interface désinstallé est actuellement actif, le paramètre d'interface dans `config.json` est réinitialisé et l'interface par défaut est restauré.

### Limitation de débit

WRITE

### Authentification

Nécessite l'authentification PIN ou la clé API, plus la requête doit provenir de localhost. Les requêtes à distance sont rejetées avec 403.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `name` | string | Nom de l'interface (paramètre de chemin). Seuls les caractères alphanumériques, les tirets et les traits de soulignement |

### Réponse

```json
{
  "name": "custom-dark",
  "uninstalled": true
}
```

### Erreurs

| Statut | Condition |
|--------|-----------|
| 400 | Nom de l'interface invalide, ou tentative de désinstallation de `default` |
| 403 | La requête ne provient pas de localhost |
| 404 | L'interface spécifiée n'existe pas |
