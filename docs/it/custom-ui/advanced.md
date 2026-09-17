# Guida Avanzata — SSE, Operazioni Batch e Sicurezza

Funzionalità avanzate e pattern di implementazione per le UI personalizzate.

## Aggiornamenti in Tempo Reale (SSE)

Con i Server-Sent Events puoi ricevere in tempo reale i progressi della scansione, le modifiche ai preferiti, l'avanzamento dell'analisi AI e altro.

### Metodo di Connessione

```javascript
// Utilizzo diretto di EventSource (sicuro nelle UI personalizzate)
const sse = new EventSource('/api/events/stream');

// Sottoscrizione agli eventi
sse.addEventListener('scan.progress', (e) => {
  const data = JSON.parse(e.data);
  console.log(`Scan: ${data.scanned}/${data.total}`);
});

sse.addEventListener('scan.complete', (e) => {
  const data = JSON.parse(e.data);
  console.log(`Scan done: ${data.added_count} added`);
  // Ricarica la griglia
  reloadResults();
});
```

**Nota**: Nell'UI di riferimento (`ui/default/`), `window.EventSource` è sovrascritto da un Proxy, quindi `new EventSource()` non è utilizzabile. Nelle UI personalizzate questa limitazione non si applica e puoi usarlo direttamente.

### Elenco degli Eventi Principali

| Evento | Dati | Utilizzo nell'UI |
|--------|------|-----------------|
| `scan.progress` | `{ scanned, total, current_file }` | Visualizzazione della barra di avanzamento |
| `scan.complete` | `{ added_count, updated_count }` | Ricarica dei risultati di ricerca |
| `favorite.add` | `{ file_id, collection_id }` | Aggiornamento icona preferito |
| `favorite.remove` | `{ file_id, collection_id }` | Aggiornamento icona preferito |
| `collection.create` | `{ id, name }` | Aggiornamento lista collezioni |

Per tutti i tipi di evento, consulta [events.md](../api/events.md).

### Gestione della Connessione

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
      // Riconnessione (backoff esponenziale)
      setTimeout(() => this.connect(), 3000);
    };
    // Ripristino degli handler registrati
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

// Esempio di utilizzo
const sse = new SSEConnection();
sse.on('scan.progress', (data) => updateProgressBar(data));
sse.on('scan.complete', () => reloadResults());
```

### Connessione Visibility-aware

Sospendi la connessione quando il tab è nascosto per risparmiare risorse:

```javascript
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    sse.close();
  } else {
    sse.connect();
  }
});
```

## Operazioni Batch

Pattern API per eseguire operazioni su più file contemporaneamente.

### Impostazione Rating in Blocco

```javascript
async function batchRate(items) {
  // items: [{file_id: 1, rating: 5}, {file_id: 2, rating: 3}]
  // Massimo 500 elementi
  const res = await api('/api/ratings/batch-set', {
    method: 'POST',
    body: JSON.stringify({ items }),
  });
  return res;
}
```

### Operazioni sui Tag in Blocco

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

### Operazioni sulle Collezioni in Blocco

```javascript
// Aggiunta a una collezione
async function addToCollection(collectionId, fileIds) {
  return api(`/api/collections/${collectionId}/batch-add`, {
    method: 'POST',
    body: JSON.stringify({ file_ids: fileIds }),
  });
}

// Rimozione da una collezione
async function removeFromCollection(collectionId, fileIds) {
  return api(`/api/collections/${collectionId}/batch-remove`, {
    method: 'POST',
    body: JSON.stringify({ file_ids: fileIds }),
  });
}
```

### Gestione del Successo Parziale

Le operazioni batch possono riuscire parzialmente:

```javascript
const result = await batchRate(items);
if (result.failed && result.failed.length > 0) {
  console.warn(`${result.failed.length} items failed:`, result.failed);
  showToast(`${result.succeeded} succeeded, ${result.failed.length} failed`);
}
```

## Gestione degli Errori

### Codici di Stato HTTP

| Codice | Significato | Azione |
|--------|-------------|--------|
| 200 | Successo | - |
| 304 | Not Modified | Usa la cache (thumbnail) |
| 400 | Richiesta non valida | Verifica l'input |
| 403 | Autenticazione fallita / CSRF non valido | Verifica l'header `X-Requested-With` |
| 404 | Risorsa non trovata | Verifica l'ID del file |
| 429 | Rate limit | Attendi i secondi indicati nell'header `Retry-After` |
| 500 | Errore del server | Riprova o controlla i log |

### Gestione del Rate Limit

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

### Determinazione del Formato della Risposta

Esistono due formati di risposta, vecchio e nuovo:

```javascript
function parseApiResponse(json) {
  // Nuovo formato: { ok, error, data }
  if ('ok' in json) {
    if (!json.ok) throw new Error(json.error || 'Unknown error');
    return json.data ?? json;
  }
  // Vecchio formato: { success, message }
  if ('success' in json) {
    if (!json.success) throw new Error(json.message || 'Unknown error');
    return json;
  }
  // Formato dati diretti (results ecc.)
  return json;
}
```

## Sicurezza

### Protezione CSRF

Tutte le operazioni di scrittura (POST / PUT / DELETE) richiedono l'header `X-Requested-With`:

```javascript
// Corretto: include l'header
fetch('/api/ratings/set', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
  },
  body: JSON.stringify({ file_id: 42, rating: 5 }),
});
```

**Eccezione**: Le richieste con API Key tramite header `Authorization: Bearer sk_...` non richiedono l'header CSRF.

### Prevenzione XSS

Quando si inserisce input utente o nomi di file nel DOM, è necessario eseguire il sanitizing:

```javascript
function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// Errato: inserimento diretto del nome file
card.innerHTML = `<p>${file.filename}</p>`;  // Rischio XSS

// Corretto: escape
card.innerHTML = `<p>${escapeHtml(file.filename)}</p>`;

// Ancora meglio: usa le API DOM
const p = document.createElement('p');
p.textContent = file.filename;  // Escape automatico
card.appendChild(p);
```

### Gestione delle API Key

Se utilizzi API Key nelle UI personalizzate, non incorporarle lato client.
Nelle UI basate su browser, usa normalmente l'autenticazione PIN / sessione e proteggile con gli header CSRF.

## Implementazione della Funzionalità di Ricerca

### Ricerca Base

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

### Autocompletamento

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

### Cambio Ordinamento

```javascript
const SORT_OPTIONS = [
  { value: 'date', label: 'Date (New)' },
  { value: 'name', label: 'Name' },
  { value: 'size', label: 'Size' },
  { value: 'rating', label: 'Rating' },
  { value: 'random', label: 'Random' },
];
```

## Gestione delle Collezioni

```javascript
// Recupero lista collezioni
async function getCollections() {
  const res = await fetch('/api/collections');
  return res.json();
}

// Creazione collezione
async function createCollection(name) {
  return api('/api/collections', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

// Ricerca all'interno di una collezione
async function searchInCollection(collectionId, query = '') {
  return search(query, { collection: collectionId });
}
```

## Conversione dei Prompt

Conversione del formato prompt tra A1111 e NAI:

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

## Distribuzione

### Distribuzione dell'UI Personalizzata

Per distribuire la tua UI personalizzata ad altri utenti:

1. **Repository Git**: Carica su GitHub ecc. → Installa dall'UI delle Impostazioni
2. **Archivio ZIP**: Comprimi i file in ZIP e condividi l'URL di download
3. **Copia manuale**: Copia direttamente nella directory `ui/<name>/`

### Installazione

Installa dalla scheda "UI" nella pagina Impostazioni, oppure tramite API:

```bash
# Installazione con curl
curl -X POST http://localhost:5000/api/ui/install \
  -H "X-Requested-With: XMLHttpRequest" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/user/my-custom-ui.git"}'
```

### Requisiti di manifest.json

Il `manifest.json` dell'UI da distribuire deve includere:

```json
{
  "name": "my-custom-ui",
  "version": "1.0.0",
  "description": "A beautiful custom UI for YU AI Manager",
  "author": "Your Name",
  "api_version": "1"
}
```

- `name` e `version` sono obbligatori
- `name` diventa anche il nome della directory di installazione
- `"default"` è un nome riservato e non può essere usato
