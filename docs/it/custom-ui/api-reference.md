# Riferimento API — Raccolta link per sviluppatori Custom UI

Raccolta link di documentazione API per lo sviluppo di UI personalizzata e tabella di consultazione rapida per le API più usate.

## Elenco documentazione

### Convenzioni comuni

- [Convenzioni API comuni](../api/README.md) — Base URL, autenticazione (4 metodi), protezione CSRF, rate limit, formato risposta, paginazione

### Per endpoint

- [API Ricerca](../api/search.md) — GET /api/search, suggerisci, raggruppa, server-info
- [API File](../api/files.md) — Dettagli file, miniatura, originale, conversione prompt
- [API Scansione](../api/scan.md) — Controllo scansione, gestione root scansione, backfill hash
- [API Eventi](../api/events.md) — SSE eventi real-time, stream log

### Tema

- [Elenco variabili CSS](../api/theming.md) — Proprietà custom tema (Light/Dark)

## Tabella di consultazione rapida API

### Lettura (GET, no auth richiesta*)

| Endpoint | Utilizzo | Parametri principali |
|--------------|------|---------------|
| `/api/search` | Ricerca file | `q`, `sort`, `limit`, `cursor`, `rating_min`, `collection_id` |
| `/api/thumbnail/<id>` | Immagine miniatura (WebP) | `size` (default 300) |
| `/api/original/<id>` | File originale | Range support |
| `/api/file/<id>` | Dettagli file | — |
| `/api/suggest` | Suggerimento tag | `q`, `limit` |
| `/api/stats/all` | Informazioni statistiche | — |
| `/api/collections` | Elenco collezioni | — |
| `/api/server-info` | Informazioni server | — |
| `/api/events/stream` | Stream SSE | `types` |

*In ambienti senza PIN, o dopo autenticazione sessione

### Scrittura (POST, header `X-Requested-With` obbligatorio)

| Endpoint | Utilizzo | Esempio corpo |
|--------------|------|---------|
| `/api/ratings/set` | Imposta rating | `{file_id: 42, rating: 5}` |
| `/api/ratings/batch-set` | Rating batch | `{items: [{file_id, rating}, ...]}` |
| `/api/favorites/add` | Aggiungi preferiti | `{file_id: 42}` |
| `/api/favorites/remove` | Rimuovi preferiti | `{file_id: 42}` |
| `/api/tags/batch-set` | Operazioni tag batch | `{items: [{file_id, add: [], remove: []}]}` |
| `/api/collections` | Crea collezione | `{name: "My Collection"}` |
| `/api/collections/<id>/batch-add` | Aggiungi a collezione | `{file_ids: [1, 2, 3]}` |
| `/api/scan-all` | Avvia scansione | `{}` |
| `/api/convert` | Converti prompt | `{prompt, direction}` |

### Gestione UI

| Endpoint | Metodo | Utilizzo |
|--------------|---------|------|
| `/api/ui/list` | GET | Elenco UI |
| `/api/ui/switch` | POST | Cambia UI attiva |
| `/api/ui/install` | POST | Installa UI da URL (solo localhost) |
| `/api/ui/<name>/uninstall` | DELETE | Disinstalla UI (solo localhost) |

## Formato risposta

### Risultati ricerca

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
      rating: 4,                 // 0-5 (0 = unrated)
      is_favorite: true,
      tags: ["landscape", "sunset"]
    }
  ],
  total: 1500,
  next_cursor: "base64token..."  // null = last page
}
```

### Miniatura

```
GET /api/thumbnail/42
→ Content-Type: image/webp
→ ETag: "abc123"
→ Cache-Control: max-age=86400
```

Il browser metterà in cache automaticamente. Puoi referenziare direttamente nei tag `<img>`:

```html
<img src="/api/thumbnail/42" loading="lazy" alt="thumbnail">
```

### Risposta errore

```javascript
{
  ok: false,
  error: "Rate limit exceeded",
  code: "RATE_LIMIT",      // optional
  detail: "Retry after 5s"  // optional
}
```

## Nota su header CSRF

```javascript
// Helper header comune
const API_HEADERS = {
  'Content-Type': 'application/json',
  'X-Requested-With': 'XMLHttpRequest',
};

// GET: header non richiesto
fetch('/api/search?q=test');

// POST: X-Requested-With obbligatorio
fetch('/api/ratings/set', {
  method: 'POST',
  headers: API_HEADERS,
  body: JSON.stringify({ file_id: 42, rating: 5 }),
});
```
