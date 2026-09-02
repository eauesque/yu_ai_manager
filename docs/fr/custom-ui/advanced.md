# Guide Avancé — SSE, Opérations par Lot, Sécurité

Fonctionnalités avancées et modèles d'implémentation pour les interfaces utilisateur personnalisées.

## Mises à Jour en Temps Réel (SSE)

Avec Server-Sent Events, vous pouvez recevoir en temps réel la progression des analyses, les changements de favoris, la progression des analyses IA, etc.

### Méthode de Connexion

```javascript
// Utiliser EventSource directement (sûr dans les UI personnalisées)
const sse = new EventSource('/api/events/stream');

// Abonnement aux événements
sse.addEventListener('scan.progress', (e) => {
  const data = JSON.parse(e.data);
  console.log(`Scan: ${data.scanned}/${data.total}`);
});

sse.addEventListener('scan.complete', (e) => {
  const data = JSON.parse(e.data);
  console.log(`Scan done: ${data.added_count} added`);
  // Recharger la grille
  reloadResults();
});
```

**Remarque** : Dans l'UI de référence (`ui/default/`), `window.EventSource` est remplacé par un Proxy, donc `new EventSource()` ne peut pas être utilisé. Cette restriction ne s'applique pas aux UI personnalisées, vous pouvez donc l'utiliser directement.

### Liste des Principaux Événements

| Événement | Données | Usage dans l'UI |
|---------|--------|------------|
| `scan.progress` | `{ scanned, total, current_file }` | Affichage de la barre de progression |
| `scan.complete` | `{ added_count, updated_count }` | Rechargement des résultats de recherche |
| `favorite.add` | `{ file_id, collection_id }` | Mise à jour de l'icône favori |
| `favorite.remove` | `{ file_id, collection_id }` | Mise à jour de l'icône favori |
| `collection.create` | `{ id, name }` | Mise à jour de la liste des collections |

Pour tous les types d'événements, consultez [events.md](../api/events.md).

### Gestion de la Connexion

```javascript
class SSEConnection {
  constructor() {
    this.handlers = new Map();
    this.connect();
  }

  connect() {
    this.sse = new EventSource('/api/events/stream');
    this.sse.onerror = () => {
      this.sse.close();
      // Reconnexion (backoff exponentiel)
      setTimeout(() => this.connect(), 3000);
    };
    // Re-configurer les gestionnaires enregistrés
    for (const [type, handler] of this.handlers) {
      this.sse.addEventListener(type, handler);
    }
  }

  on(eventType, callback) {
    const handler = (e) => callback(JSON.parse(e.data));
    this.handlers.set(eventType, handler);
    this.sse.addEventListener(eventType, handler);
  }

  close() {
    this.sse.close();
  }
}

// Exemple d'utilisation
const sse = new SSEConnection();
sse.on('scan.progress', (data) => updateProgressBar(data));
sse.on('scan.complete', () => reloadResults());
```

### Connexion Visibility-aware

Supprimer la connexion quand l'onglet devient invisible, pour économiser les ressources :

```javascript
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    sse.close();
  } else {
    sse.connect();
  }
});
```

## Opérations par Lot

Modèles d'API pour exécuter des opérations sur plusieurs fichiers en une seule fois.

### Définition des Notes en Lot

```javascript
async function batchRate(items) {
  // items: [{file_id: 1, rating: 5}, {file_id: 2, rating: 3}]
  // Maximum 500 éléments
  const res = await api('/api/ratings/batch-set', {
    method: 'POST',
    body: JSON.stringify({ items }),
  });
  return res;
}
```

### Opérations de Tags en Lot

```javascript
async function batchSetTags(items) {
  // items: [{file_id: 1, add: ["good"], remove: ["bad"]}, ...]
  const res = await api('/api/tags/batch-set', {
    method: 'POST',
    body: JSON.stringify({ items }),
  });
  return res;
}
```

### Opérations de Collection en Lot

```javascript
// Ajouter à une collection
async function addToCollection(collectionId, fileIds) {
  return api(`/api/collections/${collectionId}/batch-add`, {
    method: 'POST',
    body: JSON.stringify({ file_ids: fileIds }),
  });
}

// Retirer d'une collection
async function removeFromCollection(collectionId, fileIds) {
  return api(`/api/collections/${collectionId}/batch-remove`, {
    method: 'POST',
    body: JSON.stringify({ file_ids: fileIds }),
  });
}
```

### Traitement des Succès Partiels

Les opérations par lot peuvent réussir partiellement :

```javascript
const result = await batchRate(items);
if (result.failed && result.failed.length > 0) {
  console.warn(`${result.failed.length} items failed:`, result.failed);
  showToast(`${result.succeeded} succeeded, ${result.failed.length} failed`);
}
```

## Gestion des Erreurs

### Codes de Statut HTTP

| Code | Signification | Action |
|--------|------|------|
| 200 | Succès | - |
| 304 | Not Modified | Utiliser le cache (miniatures) |
| 400 | Requête invalide | Vérifier l'entrée |
| 403 | Échec d'authentification / CSRF invalide | Vérifier l'en-tête `X-Requested-With` |
| 404 | Ressource inexistante | Vérifier l'ID du fichier |
| 429 | Limite de taux | Attendre le nombre de secondes de l'en-tête `Retry-After` |
| 500 | Erreur serveur | Réessayer ou vérifier les logs |

### Gestion des Limites de Taux

```javascript
async function apiWithRetry(path, options = {}, maxRetries = 3) {
  for (let i = 0; i < maxRetries; i++) {
    const res = await fetch(path, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        ...options.headers,
      },
    });

    if (res.status === 429) {
      const retryAfter = parseInt(res.headers.get('Retry-After') || '5', 10);
      console.warn(`Rate limited, retry after ${retryAfter}s`);
      await new Promise(r => setTimeout(r, retryAfter * 1000));
      continue;
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: res.statusText }));
      throw new Error(err.error || `HTTP ${res.status}`);
    }

    return res.json();
  }
  throw new Error('Max retries exceeded');
}
```

### Détection du Format de Réponse

Il existe deux types de formats de réponse, anciens et nouveaux :

```javascript
function parseApiResponse(json) {
  // Nouveau format : { ok, error, data }
  if ('ok' in json) {
    if (!json.ok) throw new Error(json.error || 'Unknown error');
    return json.data ?? json;
  }
  // Ancien format : { success, message }
  if ('success' in json) {
    if (!json.success) throw new Error(json.message || 'Unknown error');
    return json;
  }
  // Format de données directes (results, etc.)
  return json;
}
```

## Sécurité

### Protection CSRF

Toutes les opérations d'écriture (POST / PUT / DELETE) nécessitent l'en-tête `X-Requested-With` :

```javascript
// Bon exemple : avec en-tête
fetch('/api/ratings/set', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
  },
  body: JSON.stringify({ file_id: 42, rating: 5 }),
});
```

**Exception** : Les requêtes API Key avec l'en-tête `Authorization: Bearer sk_...` n'ont pas besoin de l'en-tête CSRF.

### Prévention XSS

Lors de l'insertion d'entrées utilisateur ou de noms de fichiers dans le DOM, une désinfection est nécessaire :

```javascript
function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// Mauvais exemple : insérer le nom de fichier tel quel
card.innerHTML = `<p>${file.filename}</p>`;  // Risque XSS

// Bon exemple : échappement
card.innerHTML = `<p>${escapeHtml(file.filename)}</p>`;

// Encore meilleur : utiliser l'API DOM
const p = document.createElement('p');
p.textContent = file.filename;  // Échappement automatique
card.appendChild(p);
```

### Gestion des Clés API

Lors de l'utilisation d'une API Key depuis une UI personnalisée, ne pas intégrer la clé côté client. Les UI basées sur navigateur utilisent généralement l'authentification PIN / session et sont protégées par l'en-tête CSRF.

## Implémentation de la Recherche

### Recherche de Base

```javascript
async function search(query, options = {}) {
  const params = new URLSearchParams({
    q: query,
    limit: String(options.limit || 50),
    sort: options.sort || 'date',
  });

  if (options.cursor) params.set('cursor', options.cursor);
  if (options.minRating) params.set('rating_min', String(options.minRating));
  if (options.collection) params.set('collection_id', String(options.collection));
  if (options.favOnly) params.set('favorites_only', 'true');

  const res = await fetch(`/api/search?${params}`);
  return res.json();
}
```

### Autocomplétion

```javascript
let debounceTimer;

function onSearchInput(e) {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(async () => {
    const q = e.target.value;
    if (q.length < 2) return;

    const res = await fetch(`/api/suggest?q=${encodeURIComponent(q)}&limit=10`);
    const { suggestions } = await res.json();
    showSuggestions(suggestions);  // [{value: "1girl", count: 5432}, ...]
  }, 200);
}
```

### Changement de Tri

```javascript
const SORT_OPTIONS = [
  { value: 'date', label: 'Date (New)' },
  { value: 'name', label: 'Name' },
  { value: 'size', label: 'Size' },
  { value: 'rating', label: 'Rating' },
  { value: 'random', label: 'Random' },
];
```

## Gestion des Collections

```javascript
// Obtenir la liste des collections
async function getCollections() {
  const res = await fetch('/api/collections');
  return res.json();
}

// Créer une collection
async function createCollection(name) {
  return api('/api/collections', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

// Rechercher dans une collection
async function searchInCollection(collectionId, query = '') {
  return search(query, { collection: collectionId });
}
```

## Conversion de Prompts

Conversion de format de prompt entre A1111 / NAI :

```javascript
async function convertPrompt(prompt, direction) {
  // direction: "a1111_to_nai" or "nai_to_a1111"
  const res = await api('/api/convert', {
    method: 'POST',
    body: JSON.stringify({ prompt, direction }),
  });
  return res.converted;
}
```

## Déploiement

### Distribution de l'UI Personnalisée

Pour distribuer une UI personnalisée à d'autres utilisateurs :

1. **Dépôt Git** : Push vers GitHub, etc. → Installation depuis l'UI Settings
2. **Archive ZIP** : Compresser les fichiers et partager l'URL de téléchargement
3. **Placement manuel** : Copier directement dans le répertoire `ui/<name>/`

### Installation

Onglet « UI » de la page Settings, ou installation via API :

```bash
# Installation avec curl
curl -X POST http://localhost:5000/api/ui/install \
  -H "X-Requested-With: XMLHttpRequest" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/user/my-custom-ui.git"}'
```

### Exigences de manifest.json

Le `manifest.json` des UI distribuées doit inclure les éléments suivants :

```json
{
  "name": "my-custom-ui",
  "version": "1.0.0",
  "description": "A beautiful custom UI for YU AI Manager",
  "author": "Your Name",
  "api_version": "1"
}
```

- `name` et `version` sont obligatoires
- `name` devient aussi le nom du répertoire d'installation
- `"default"` est un nom réservé et ne peut pas être utilisé
