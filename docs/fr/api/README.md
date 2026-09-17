# Référence de l'API YU AI Manager

Cette documentation de l'API REST couvre chaque fonctionnalité de YU AI Manager, disponible pour les interfaces personnalisées et les scripts.

## Conventions communes

### URL de base

```
http://<host>:<port>
```

Par défaut : `http://127.0.0.1:5000`
Environnement de test : `http://127.0.0.1:5100` (lors de l'utilisation de `config_test.json`)

### Authentification

Quatre méthodes d'authentification sont supportées :

| Méthode | Cas d'usage | Exemple d'en-tête |
|---------|----------|-------------------|
| PIN Auth | Sessions navigateur | Cookie: `session=...` |
| API Key | Communication machine-à-machine | `Authorization: Bearer sk_...` |
| Trusted Proxy | Derrière un reverse proxy | `X-Remote-User: username` |
| LAN Share Token | Accès invité | Chemin URL `/s/<token>/...` |

Il est possible de sauter l'authentification complètement en lançant avec `config_test.json` (pas de PIN).

### Protection CSRF

Toutes les requêtes `POST` / `PUT` / `DELETE` aux points d'accès `/api/` nécessitent l'en-tête `X-Requested-With` :

```
X-Requested-With: XMLHttpRequest
```

**Exception** : les requêtes de clé API avec l'en-tête `Authorization: Bearer` n'en ont pas besoin.

### Limitation de débit

| Niveau | Portée | Débit | Burst |
|--------|--------|-------|-------|
| READ | Tous les GET | Illimité | - |
| WRITE | POST/PUT/DELETE (standard) | ~120 req/min | 30 |
| HEAVY | Recherche similaire, calcul de hachage, analyse IA, analyse | ~20 req/min | 5 |
| DESTRUCTIVE | Purge, suppression forcée, effacement du cache, écriture de config | ~12 req/min | 3 |

Un en-tête `Retry-After` accompagne les réponses 429.

### Format de réponse

**Succès** (nouvelles API) :
```json
{
  "ok": true,
  "error": null,
  "data": { ... }
}
```

**Erreur** :
```json
{
  "ok": false,
  "error": "Message d'erreur",
  "code": "ERROR_CODE",
  "detail": "Détails supplémentaires (optionnel)"
}
```

Certaines API héritées retournent le format `{ "success": true, "message": "..." }`.

### Pagination

**Basée sur l'offset** (par défaut) :
```
GET /api/search?offset=0&limit=50
```

**Basée sur le curseur** (pour les grands ensembles de données) :
```
GET /api/search?cursor=<opaque_token>&limit=50
```

La réponse inclut un champ `next_cursor`.

### Opérations par lot

Les API par lot supportent jusqu'à 500 opérations par requête. Le succès partiel est possible :

```json
POST /api/ratings/batch-set
{
  "items": [
    { "file_id": 1, "rating": 5 },
    { "file_id": 999, "rating": 3 }
  ]
}
```

## Catégories d'API

| Document | Contenu |
|----------|---------|
| [search.md](search.md) | Recherche, suggestions, groupes |
| [files.md](files.md) | Détails des fichiers, miniatures, récupération média |
| [scan.md](scan.md) | Contrôle d'analyse, gestion des racines d'analyse |
| [events.md](events.md) | Flux d'événements SSE |
| [theming.md](theming.md) | Variables CSS, personnalisation du thème |
| [source.md](source.md) | Navigation du code source (lecture seule pour MCP) |
| [github.md](github.md) | Intégration GitHub (comptes, problèmes, PR, notifications, discussions, versions) |
| [scheduler.md](scheduler.md) | Planificateur de tâches (gestion des tâches, historique d'exécution) |
| [ratings.md](ratings.md) | Évaluations (définir, définir par lot, obtenir, statistiques) |
| [favorites.md](favorites.md) | Favoris (basculer, vérifier, lister) |
| [collections.md](collections.md) | Collections (CRUD, réordonner, ajouter/supprimer par lot, export CSV) |
| [tags.md](tags.md) | Étiquettes (définir par lot, suggérer) |
| [sns.md](sns.md) | Partage SNS & Moniteur Bluesky (publication, notifications, triage, réponse automatique) |
| [hailo-remote-tagger.md](hailo-remote-tagger.md) | Hailo Remote Tagger (config, marquage unique/par lot, CRUD d'étiquette) |
| [tagger-servers.md](tagger-servers.md) | Registre des serveurs de marquage (cluster d'inférence de marquage distribué, gestion des serveurs, exécution par lot) |
| [svg.md](svg.md) | Rastérisation SVG (conversion SVG en PNG/WebP, support pipeline img2img) |
| [settings.md](settings.md) | Gestion des paramètres (schéma, obtenir/mettre à jour les valeurs, chiffrement des secrets, intégration 1Password/Bitwarden) |
| [extensions.md](extensions.md) | Extensions (lister, basculer, config, installer, sécurité, marketplace, création) |
| [analysis.md](analysis.md) | Analyse IA (config, analyse unique/par lot, analyse de tendance, stats, registre des serveurs) |
| [system-update.md](system-update.md) | Mise à jour système (vérification de version, application de mise à jour, gestionnaire de mise à jour unifié) |
| [tools.md](tools.md) | Outils (détection des doublons, calcul de hachage, recherche similaire, gestion du cache, sauvegarde, nettoyage des archives, journal de débogage) |
| [agent.md](agent.md) | Agent Safety Gateway (Kill Switch, Circuit Breaker, Budget, Approbation, Scope Fence, Undo, Anomaly Detection) |
| [profiles.md](profiles.md) | Gestion des profils (CRUD, doublon, export/import QR) |
| [wd-tagger.md](wd-tagger.md) | WD-Tagger (marquage automatique Danbooru, gestion de modèle, VLM, XMP) |
| [ocr.md](ocr.md) | OCR (reconnaissance de texte, traduction, support vidéo/PDF, benchmarks, profils) |
| [apikeys.md](apikeys.md) | Gestion des clés API (créer, lister, scopes, révoquer) |
| [debug.md](debug.md) | Débogage (inspection des métadonnées, requête SQL, vérification de modèle) |
| [ui.md](ui.md) | Gestion de l'interface (lister, changer, installer, désinstaller) |
| [video-analysis.md](video-analysis.md) | Analyse vidéo (config, statut, extraction de keyframe) |

## Démarrage rapide (curl)

```bash
# Recherche (environnement sans PIN)
curl "http://localhost:5100/api/search?q=landscape&limit=10"

# Récupérer une miniature
curl "http://localhost:5100/api/thumbnail/42" -o thumb.webp

# Recherche avec clé API
curl -H "Authorization: Bearer sk_your_key_here" \
     "http://localhost:5100/api/search?q=portrait"

# Définir une évaluation
curl -X POST "http://localhost:5100/api/ratings/set" \
     -H "X-Requested-With: XMLHttpRequest" \
     -H "Content-Type: application/json" \
     -d '{"file_id": 42, "rating": 5}'
```
