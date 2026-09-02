# Référence API — Liens pour les développeurs d'UI personnalisée

Liens vers la documentation API référencée dans le développement d'UI personnalisée, et guide de référence rapide des API couramment utilisées.

## Liste de la documentation

### Conventions communes

- [Conventions API communes](../api/README.md) — URL de base, authentification (4 méthodes), protection CSRF, limite de débit, format de réponse, pagination

### Par endpoint

- [API de recherche](../api/search.md) — GET /api/search, suggestions, groupes, server-info
- [API de fichiers](../api/files.md) — détails de fichier, miniatures, original, conversion de prompt
- [API de scan](../api/scan.md) — contrôle du scan, gestion des racines de scan, remplissage des hachages
- [API d'événements](../api/events.md) — événements SSE en temps réel, flux de logs

### Thèmes

- [Liste des variables CSS](../api/theming.md) — Propriétés personnalisées de thème (clair/sombre)

## Guide de référence rapide des API

### Lecture (GET, sans authentification*)

| Endpoint | Usage | Paramètres principaux |
|--------------|------|---------------|
| `/api/search` | Recherche de fichiers | `q`, `sort`, `limit`, `cursor`, `rating_min`, `collection_id` |
| `/api/thumbnail/<id>` | Image miniature (WebP) | `size` (défaut 300) |
| `/api/original/<id>` | Fichier original | Prise en charge de Range |
| `/api/file/<id>` | Détails du fichier | — |
| `/api/suggest` | Suggestions de tags | `q`, `limit` |
| `/api/stats/all` | Informations statistiques | — |
| `/api/collections` | Liste des collections | — |
| `/api/server-info` | Informations serveur | — |
| `/api/events/stream` | Flux SSE | `types` |

*En environnement sans PIN, ou si l'authentification de session est établie

### Écriture (POST, en-tête `X-Requested-With` obligatoire)

| Endpoint | Usage | Exemple de corps |
|--------------|------|---------|
| `/api/ratings/set` | Définir une note | `{file_id: 42, rating: 5}` |
| `/api/ratings/batch-set` | Notes en masse | `{items: [{file_id, rating}, ...]}` |
| `/api/favorites/add` | Ajouter aux favoris | `{file_id: 42}` |
| `/api/favorites/remove` | Retirer des favoris | `{file_id: 42}` |
| `/api/tags/batch-set` | Opérations de tags en masse | `{items: [{file_id, add: [], remove: []}]}` |
| `/api/collections` | Créer une collection | `{name: "Ma Collection"}` |
| `/api/collections/<id>/batch-add` | Ajouter à une collection | `{file_ids: [1, 2, 3]}` |
| `/api/scan-all` | Démarrer le scan | `{}` |
| `/api/convert` | Conversion de prompt | `{prompt, direction}` |

### Gestion de l'UI

| Endpoint | Méthode | Usage |
|--------------|---------|------|
| `/api/ui/list` | GET | Liste des UI |
| `/api/ui/switch` | POST | Changer d'UI |
| `/api/ui/install` | POST | Installer une UI (localhost uniquement) |
| `/api/ui/<name>/uninstall` | DELETE | Désinstaller une UI (localhost uniquement) |

## Format de réponse

### Résultats de recherche

```javascript
{
  results: [
    {
      id: 42,
      path: "/images/00042.png",
      filename: "00042.png",
      width: 1024,
      height: 1536,
      meta_type: "a1111_png",   // a1111_png, novelai_v4_png, comfy_png, unknown
      model_name: "animagine-xl-3.1",
      positive: "1girl, landscape",
      rating: 4,                 // 0-5 (0 = non noté)
      is_favorite: true,
      tags: ["landscape", "sunset"]
    }
  ],
  total: 1500,
  next_cursor: "base64token..."  // null = dernière page
}
```

### Miniature

```
GET /api/thumbnail/42
→ Content-Type: image/webp
→ ETag: "abc123"
→ Cache-Control: max-age=86400
```

Le navigateur met automatiquement en cache. Référençable directement dans une balise `<img>` :

```html
<img src="/api/thumbnail/42" loading="lazy" alt="miniature">
```

### Réponse d'erreur

```javascript
{
  ok: false,
  error: "Rate limit exceeded",
  code: "RATE_LIMIT",      // optionnel
  detail: "Retry after 5s"  // optionnel
}
```

## Remarque sur l'en-tête CSRF

```javascript
// Helper d'en-têtes communs
const API_HEADERS = {
  'Content-Type': 'application/json',
  'X-Requested-With': 'XMLHttpRequest',
};

// GET : pas d'en-tête nécessaire
fetch('/api/search?q=test');

// POST : X-Requested-With obligatoire
fetch('/api/ratings/set', {
  method: 'POST',
  headers: API_HEADERS,
  body: JSON.stringify({ file_id: 42, rating: 5 }),
});
```
