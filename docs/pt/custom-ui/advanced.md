# Guia Avançado — SSE, Operações em Lote e Segurança

Funcionalidades avançadas e padrões de implementação para UIs personalizadas.

## Atualizações em Tempo Real (SSE)

Você pode receber atualizações em tempo real do progresso de varredura, alterações de favoritos, progresso de análise de IA, etc. via Server-Sent Events.

### Como Conectar

```javascript
// Use EventSource diretamente (é seguro em UIs personalizadas)
const sse = new EventSource('/api/events/stream');

// Assinar eventos
sse.addEventListener('scan.progress', (e) => {
  const data = JSON.parse(e.data);
  console.log(`Scan: ${data.scanned}/${data.total}`);
});

sse.addEventListener('scan.complete', (e) => {
  const data = JSON.parse(e.data);
  console.log(`Scan done: ${data.added_count} added`);
  // Recarregar grid
  reloadResults();
});
```

**Nota**: Na UI de referência (`ui/default/`), o `window.EventSource` foi substituído por um Proxy, portanto `new EventSource()` não pode ser usado. Essa restrição não se aplica a UIs personalizadas, portanto você pode usá-lo diretamente.

### Lista de Eventos Principais

| Evento | Dados | Uso na UI |
|---------|--------|------------|
| `scan.progress` | `{ scanned, total, current_file }` | Exibir barra de progresso |
| `scan.complete` | `{ added_count, updated_count }` | Recarregar resultados de pesquisa |
| `favorite.add` | `{ file_id, collection_id }` | Atualizar ícone de favorito |
| `favorite.remove` | `{ file_id, collection_id }` | Atualizar ícone de favorito |
| `collection.create` | `{ id, name }` | Atualizar lista de coleções |

Consulte [events.md](../api/events.md) para todos os tipos de eventos.

### Gerenciamento de Conexão

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
      // Reconectar (backoff exponencial)
      setTimeout(() => this.connect(), 3000);
    };
    // Reconfigurar handlers registrados
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

// Exemplo de uso
const sse = new SSEConnection();
sse.on('scan.progress', (data) => updateProgressBar(data));
sse.on('scan.complete', () => reloadResults());
```

### Conexão Ciente de Visibilidade

Suspender conexão quando a aba fica oculta para economizar recursos:

```javascript
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    sse.close();
  } else {
    sse.connect();
  }
});
```

## Operações em Lote

Padrões de API para executar operações em vários arquivos ao mesmo tempo.

### Definição de Avaliação em Lote

```javascript
async function batchRate(items) {
  // items: [{file_id: 1, rating: 5}, {file_id: 2, rating: 3}]
  // Máximo de 500 itens
  const res = await api('/api/ratings/batch-set', {
    method: 'POST',
    body: JSON.stringify({ items }),
  });
  return res;
}
```

### Operações de Tags em Lote

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

### Operações de Coleção em Lote

```javascript
// Adicionar à coleção
async function addToCollection(collectionId, fileIds) {
  return api(`/api/collections/${collectionId}/batch-add`, {
    method: 'POST',
    body: JSON.stringify({ file_ids: fileIds }),
  });
}

// Remover da coleção
async function removeFromCollection(collectionId, fileIds) {
  return api(`/api/collections/${collectionId}/batch-remove`, {
    method: 'POST',
    body: JSON.stringify({ file_ids: fileIds }),
  });
}
```

### Tratando Sucesso Parcial

Operações em lote podem ter sucesso parcial:

```javascript
const result = await batchRate(items);
if (result.failed && result.failed.length > 0) {
  console.warn(`${result.failed.length} items failed:`, result.failed);
  showToast(`${result.succeeded} succeeded, ${result.failed.length} failed`);
}
```

## Tratamento de Erros

### Códigos de Status HTTP

| Código | Significado | Ação |
|--------|------|------|
| 200 | Sucesso | - |
| 304 | Not Modified | Usar cache (miniaturas) |
| 400 | Requisição inválida | Verificar entrada |
| 403 | Falha de autenticação / CSRF inválido | Verificar header `X-Requested-With` |
| 404 | Recurso não encontrado | Verificar ID do arquivo |
| 429 | Rate limit | Aguardar segundos indicados no header `Retry-After` |
| 500 | Erro do servidor | Tentar novamente ou verificar logs |

### Tratando Rate Limit

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

### Determinando o Formato de Resposta

Existem dois tipos de formato de resposta:

```javascript
function parseApiResponse(json) {
  // Novo formato: { ok, error, data }
  if ('ok' in json) {
    if (!json.ok) throw new Error(json.error || 'Unknown error');
    return json.data ?? json;
  }
  // Formato antigo: { success, message }
  if ('success' in json) {
    if (!json.success) throw new Error(json.message || 'Unknown error');
    return json;
  }
  // Formato de dados direto (results, etc.)
  return json;
}
```

## Segurança

### Proteção CSRF

O header `X-Requested-With` é obrigatório para todas as operações de escrita (POST / PUT / DELETE):

```javascript
// Bom exemplo: inclui o header
fetch('/api/ratings/set', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
  },
  body: JSON.stringify({ file_id: 42, rating: 5 }),
});
```

**Exceção**: Requisições com API Key usando `Authorization: Bearer sk_...` não precisam do header CSRF.

### Prevenção de XSS

É necessário sanitizar a entrada do usuário e nomes de arquivos antes de inseri-los no DOM:

```javascript
function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// Mau exemplo: inserir nome de arquivo diretamente
card.innerHTML = `<p>${file.filename}</p>`;  // Risco de XSS

// Bom exemplo: escapar
card.innerHTML = `<p>${escapeHtml(file.filename)}</p>`;

// Ainda melhor: usar API do DOM
const p = document.createElement('p');
p.textContent = file.filename;  // Escape automático
card.appendChild(p);
```

### Manuseio de API Keys

Ao usar API Keys de uma UI personalizada, não embutas a chave no lado do cliente.
UIs baseadas em navegador geralmente usam autenticação por PIN/sessão e são protegidas com headers CSRF.

## Implementando Funcionalidade de Pesquisa

### Pesquisa Básica

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

### Autocompletar

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

### Alternar Ordenação

```javascript
const SORT_OPTIONS = [
  { value: 'date', label: 'Date (New)' },
  { value: 'name', label: 'Name' },
  { value: 'size', label: 'Size' },
  { value: 'rating', label: 'Rating' },
  { value: 'random', label: 'Random' },
];
```

## Gerenciamento de Coleções

```javascript
// Obter lista de coleções
async function getCollections() {
  const res = await fetch('/api/collections');
  return res.json();
}

// Criar coleção
async function createCollection(name) {
  return api('/api/collections', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

// Pesquisar dentro de uma coleção
async function searchInCollection(collectionId, query = '') {
  return search(query, { collection: collectionId });
}
```

## Conversão de Prompts

Conversão de formato de prompt entre A1111 / NAI:

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

## Deploy

### Distribuindo UIs Personalizadas

Para distribuir sua UI personalizada para outros usuários:

1. **Repositório Git**: Fazer push para GitHub, etc. → Instalar pela UI de configurações
2. **Arquivo ZIP**: Compactar os arquivos e compartilhar a URL de download
3. **Posicionamento manual**: Copiar diretamente para o diretório `ui/<name>/`

### Instalação

Instale pela aba "UI" na página de configurações, ou via API:

```bash
# Instalar via curl
curl -X POST http://localhost:5000/api/ui/install \
  -H "X-Requested-With: XMLHttpRequest" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/user/my-custom-ui.git"}'
```

### Requisitos do manifest.json

Inclua o seguinte no `manifest.json` da UI distribuída:

```json
{
  "name": "my-custom-ui",
  "version": "1.0.0",
  "description": "A beautiful custom UI for YU AI Manager",
  "author": "Your Name",
  "api_version": "1"
}
```

- `name` e `version` são obrigatórios
- `name` também se torna o nome do diretório de instalação
- `"default"` é um nome reservado e não pode ser usado
