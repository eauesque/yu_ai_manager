# Vue d'ensemble de l'API

YU AI Manager fournit une API REST permettant d'exécuter par programme toutes les opérations de la WebUI.
Plus de 320 endpoints sont disponibles, couvrant un large éventail d'opérations allant de la gestion d'images à l'analyse IA.

> **Conseil** : Pour les conventions communes détaillées (authentification, CSRF, limite de débit, format de réponse), consultez la section « Référence API ».

## Authentification

4 méthodes d'authentification sont prises en charge.

| Méthode | Usage | En-tête/Paramètre |
|------|------|-------------------|
| Authentification PIN | Session navigateur | Connexion via `/_pin` → cookie de session |
| Clé API | Communication machine à machine, MCP | `Authorization: Bearer sk_xxxx` |
| Trusted Proxy | Proxy inverse | En-tête `X-Remote-User` |
| Token LAN Share | Accès invité | Chemin `/s/<token>` |

### Exemple de test avec curl

```bash
# Authentification par clé API (en-tête CSRF non nécessaire)
curl -H "Authorization: Bearer sk_your_key" \
     http://localhost:5000/api/search?tags=1girl

# Environnement avec authentification PIN — 2 étapes nécessaires
# 1. Obtenir le token CSRF
curl -c cookies.txt http://localhost:5000/_pin
# 2. Envoyer le PIN
curl -b cookies.txt -X POST \
     -H "X-Requested-With: XMLHttpRequest" \
     -d "pin=1234" http://localhost:5000/_pin_check
```

### Protection CSRF

L'en-tête `X-Requested-With` est obligatoire pour tous les endpoints `/api/` en POST/PUT/DELETE.
Non requis pour les requêtes avec clé API Bearer.

## Endpoints principaux

### Recherche et navigation d'images

| Méthode | Chemin | Description |
|---------|------|------|
| GET | `/api/search` | Recherche filtrée par tags, dates, notes, etc. |
| GET | `/api/search-grouped` | Recherche groupée par dossier/ZIP |
| GET | `/api/file/<id>` | Récupérer les métadonnées détaillées d'une image |
| GET | `/api/thumbnail/<id>` | Récupérer la miniature (WebP, cache ETag) |
| GET | `/api/original/<id>` | Récupérer l'image originale (support requêtes Range) |
| GET | `/api/suggest` | Suggestions d'autocomplétion de tags |

### Notes, tags et annotations

| Méthode | Chemin | Description |
|---------|------|------|
| POST | `/api/ratings/batch-set` | Définition en masse des notes |
| POST | `/api/tags/batch-set` | Édition en masse des tags |
| POST | `/api/annotations/batch-set` | Définition en masse des annotations |
| GET | `/api/annotations/<id>` | Récupérer les annotations |
| GET | `/api/annotations/search` | Rechercher les annotations |

### Collections

| Méthode | Chemin | Description |
|---------|------|------|
| GET | `/api/collections` | Liste des collections |
| POST | `/api/collections` | Créer une collection |
| PUT | `/api/collections/<id>` | Renommer une collection |
| DELETE | `/api/collections/<id>` | Supprimer une collection |
| POST | `/api/collections/<id>/batch-add` | Ajout en masse de fichiers |
| POST | `/api/collections/<id>/batch-remove` | Suppression en masse de fichiers |

### Scan

| Méthode | Chemin | Description |
|---------|------|------|
| POST | `/api/scan/start` | Démarrer le scan |
| GET | `/api/scan/status` | Obtenir la progression du scan |
| POST | `/api/scan/cancel` | Annuler le scan |
| POST | `/api/scan/resume` | Reprendre le scan interrompu |
| GET | `/api/scan-roots` | Liste des racines de scan |
| POST | `/api/scan-roots` | Ajouter une racine de scan |

### Analyse IA

| Méthode | Chemin | Description |
|---------|------|------|
| POST | `/api/analysis/analyze/<id>` | Exécuter l'analyse IA d'une image |
| GET | `/api/analysis/result/<id>` | Récupérer le résultat de l'analyse |
| POST | `/api/analysis/batch` | Analyse en lot |
| POST | `/api/wd-tagger/tag/<id>` | Inférence WD-Tagger |
| POST | `/api/wd-tagger/batch` | Inférence WD-Tagger en lot |
| POST | `/api/analysis/batch/cancel` | Annuler le lot d'analyse IA |
| POST | `/api/wd-tagger/batch/cancel` | Annuler le lot WD-Tagger |
| POST | `/api/tagger-servers/batch/cancel` | Annuler le lot de cluster tagger |
| POST | `/api/ocr/<id>` | Exécuter l'OCR |

### Paramètres

| Méthode | Chemin | Description |
|---------|------|------|
| GET | `/api/settings/schema` | Récupérer le schéma de paramètres |
| GET | `/api/settings/all` | Récupérer toutes les valeurs de paramètres |
| GET | `/api/settings/<key>` | Récupérer une valeur de paramètre |
| PUT | `/api/settings/<key>` | Mettre à jour une valeur de paramètre |

### Gestion des Extensions

| Méthode | Chemin | Description |
|---------|------|------|
| GET | `/api/extensions` | Liste des extensions |
| POST | `/api/extensions/<name>/toggle` | Activer/désactiver |
| POST | `/api/extensions/install` | Installer depuis un dépôt Git |
| DELETE | `/api/extensions/<name>/uninstall` | Désinstaller |

### Mécanismes de sécurité agent

| Méthode | Chemin | Description |
|---------|------|------|
| POST | `/api/agent/kill` | Activer le Kill Switch |
| POST | `/api/agent/resume` | Désactiver le Kill Switch |
| GET | `/api/agent/status` | Statut des mécanismes de sécurité |
| GET | `/api/agent/journal` | Journal des opérations |
| POST | `/api/agent/undo/<journal_id>` | Annuler une opération |

## Format de réponse

Toutes les API répondent dans un format JSON unifié.

```json
{
  "ok": true,
  "data": { ... },
  "error": null
}
```

En cas d'erreur :

```json
{
  "ok": false,
  "data": null,
  "error": "Message d'erreur"
}
```

## Limite de débit

Système de bucket de tokens à 3 niveaux.

| Niveau | Cible | Limite | Burst |
|--------|------|------|---------|
| READ | Toutes les requêtes GET | Illimité | - |
| WRITE | POST/PUT/DELETE | ~120 req/min | 30 |
| HEAVY | Recherche similaire, analyse IA, scan | ~20 req/min | 5 |
| DESTRUCTIVE | purge, hard-delete, écriture config | ~12 req/min | 3 |

HTTP 429 est retourné en cas de dépassement. Vérifier le nombre de secondes d'attente avec l'en-tête `Retry-After`.

## SSE (Server-Sent Events)

Les événements en temps réel sont distribués via SSE depuis `/api/events/stream`.
Consulter la section « Événements SSE » pour les détails.

> **Note** : Maximum 10 connexions simultanées par IP. Limite de taille d'upload : 100 MB.

## Documentation interne de conception

Les décisions détaillées de conception de l'API, les optimisations de performance SQLite, les connaissances de développement sur la conception du schéma DB, etc. sont consultables dans [MD Viewer](/ext/md-viewer/).
