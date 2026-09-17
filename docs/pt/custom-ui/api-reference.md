# Referência da API — Links para Desenvolvedores de UI Personalizada

Links para documentação de API referenciada no desenvolvimento de UIs personalizadas e uma visão geral rápida das APIs mais usadas.

## Lista de Documentação

### Convenções Comuns

- [Convenções Comuns da API](../api/README.md) — URL base, autenticação (4 métodos), proteção CSRF, rate limiting, formato de resposta, paginação

### Por Endpoint

- [API de Pesquisa](../api/search.md) — GET /api/search, sugestões, grupos, server-info
- [API de Arquivos](../api/files.md) — detalhes de arquivo, miniaturas, original, conversão de prompts
- [API de Varredura](../api/scan.md) — controle de varredura, gerenciamento de raízes de varredura, preenchimento de hash
- [API de Eventos](../api/events.md) — eventos SSE em tempo real, stream de logs

### Temas

- [Lista de Variáveis CSS](../api/theming.md) — propriedades personalizadas de tema (Light/Dark)

## Referência Rápida das APIs Mais Usadas

### Leitura (GET, sem autenticação necessária*)

| Endpoint | Uso | Parâmetros Principais |
|--------------|------|---------------|
| `/api/search` | Pesquisa de arquivos | `q`, `sort`, `limit`, `cursor`, `rating_min`, `collection_id` |
| `/api/thumbnail/<id>` | Imagem em miniatura (WebP) | `size` (padrão 300) |
| `/api/original/<id>` | Arquivo original | Suporte a Range |
| `/api/file/<id>` | Detalhes do arquivo | — |
| `/api/suggest` | Sugestão de tags | `q`, `limit` |
| `/api/stats/all` | Informações de estatísticas | — |
| `/api/collections` | Lista de coleções | — |
| `/api/server-info` | Informações do servidor | — |
| `/api/events/stream` | Stream SSE | `types` |

*Ambiente sem PIN ou com autenticação de sessão

### Escrita (POST, header `X-Requested-With` obrigatório)

| Endpoint | Uso | Exemplo de Body |
|--------------|------|---------|
| `/api/ratings/set` | Definir avaliação | `{file_id: 42, rating: 5}` |
| `/api/ratings/batch-set` | Avaliações em lote | `{items: [{file_id, rating}, ...]}` |
| `/api/favorites/add` | Adicionar favorito | `{file_id: 42}` |
| `/api/favorites/remove` | Remover favorito | `{file_id: 42}` |
| `/api/tags/batch-set` | Operação de tags em lote | `{items: [{file_id, add: [], remove: []}]}` |
| `/api/collections` | Criar coleção | `{name: "My Collection"}` |
| `/api/collections/<id>/batch-add` | Adicionar à coleção | `{file_ids: [1, 2, 3]}` |
| `/api/scan-all` | Iniciar varredura | `{}` |
| `/api/convert` | Conversão de prompt | `{prompt, direction}` |

### Gerenciamento de UI

| Endpoint | Método | Uso |
|--------------|---------|------|
| `/api/ui/list` | GET | Lista de UIs |
| `/api/ui/switch` | POST | Alternar UI |
| `/api/ui/install` | POST | Instalar UI (somente localhost) |
| `/api/ui/<name>/uninstall` | DELETE | Desinstalar UI (somente localhost) |

## Formato de Resposta

### Resultados de Pesquisa

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
      rating: 4,                 // 0-5 (0 = sem avaliação)
      is_favorite: true,
      tags: ["landscape", "sunset"]
    }
  ],
  total: 1500,
  next_cursor: "base64token..."  // null = última página
}
```

### Miniaturas

```
GET /api/thumbnail/42
→ Content-Type: image/webp
→ ETag: "abc123"
→ Cache-Control: max-age=86400
```

O navegador faz cache automaticamente. Pode ser referenciado diretamente em tags `<img>`:

```html
<img src="/api/thumbnail/42" loading="lazy" alt="thumbnail">
```

### Resposta de Erro

```javascript
{
  ok: false,
  error: "Rate limit exceeded",
  code: "RATE_LIMIT",      // opcional
  detail: "Retry after 5s"  // opcional
}
```

## Nota sobre o Header CSRF

```javascript
// Helper de headers comuns
const API_HEADERS = {
  'Content-Type': 'application/json',
  'X-Requested-With': 'XMLHttpRequest',
};

// GET: header não necessário
fetch('/api/search?q=test');

// POST: X-Requested-With obrigatório
fetch('/api/ratings/set', {
  method: 'POST',
  headers: API_HEADERS,
  body: JSON.stringify({ file_id: 42, rating: 5 }),
});
```
