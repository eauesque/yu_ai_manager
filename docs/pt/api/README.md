# Referência de API do YU AI Manager

Esta documentação de API REST cobre todos os recursos do YU AI Manager, disponíveis para UIs personalizadas e scripts.

## Convenções Comuns

### URL Base

```
http://<host>:<port>
```

Padrão: `http://127.0.0.1:5000`
Ambiente de teste: `http://127.0.0.1:5100` (ao usar `config_test.json`)

### Autenticação

Quatro métodos de autenticação são suportados:

| Método | Caso de Uso | Exemplo de Header |
|--------|----------|----------------|
| PIN Auth | Sessões de navegador | Cookie: `session=...` |
| API Key | Comunicação máquina para máquina | `Authorization: Bearer sk_...` |
| Proxy Confiável | Atrás de um proxy reverso | `X-Remote-User: username` |
| LAN Share Token | Acesso de convidado | Caminho URL `/s/<token>/...` |

É possível ignorar a autenticação totalmente iniciando com `config_test.json` (sem PIN).

### Proteção CSRF

Todas as requisições `POST` / `PUT` / `DELETE` para endpoints `/api/` requerem o header `X-Requested-With`:

```
X-Requested-With: XMLHttpRequest
```

**Exceção**: Requisições de API Key com o header `Authorization: Bearer` não requerem CSRF.

### Limitação de Taxa

| Camada | Escopo | Taxa | Burst |
|------|-------|------|-------|
| READ | Todo GET | Ilimitado | - |
| WRITE | POST/PUT/DELETE (padrão) | ~120 req/min | 30 |
| HEAVY | Busca similar, computação de hash, análise de IA, scan | ~20 req/min | 5 |
| DESTRUCTIVE | Purge, hard-delete, limpeza de cache, escrita de config | ~12 req/min | 3 |

Um header `Retry-After` acompanha respostas 429.

### Formato de Resposta

**Sucesso** (novas APIs):
```json
{
  "ok": true,
  "error": null,
  "data": { ... }
}
```

**Erro**:
```json
{
  "ok": false,
  "error": "Mensagem de erro",
  "code": "ERROR_CODE",
  "detail": "Detalhes adicionais (opcional)"
}
```

Algumas APIs legadas retornam formato `{ "success": true, "message": "..." }`.

### Paginação

**Baseada em Offset** (padrão):
```
GET /api/search?offset=0&limit=50
```

**Baseada em Cursor** (para grandes conjuntos de dados):
```
GET /api/search?cursor=<opaque_token>&limit=50
```

A resposta inclui um campo `next_cursor`.

### Operações em Lote

APIs em lote suportam até 500 operações por requisição. Sucesso parcial é possível:

```json
POST /api/ratings/batch-set
{
  "items": [
    { "file_id": 1, "rating": 5 },
    { "file_id": 999, "rating": 3 }
  ]
}
```

## Categorias de API

| Documento | Conteúdo |
|----------|---------|
| [search.md](search.md) | Busca, sugestões, grupos |
| [files.md](files.md) | Detalhes de arquivo, miniaturas, recuperação de mídia |
| [scan.md](scan.md) | Controle de scan, gerenciamento de raiz de scan |
| [events.md](events.md) | Fluxo de evento SSE |
| [theming.md](theming.md) | Variáveis CSS, personalização de tema |
| [source.md](source.md) | Navegação de código-fonte (somente leitura para MCP) |
| [github.md](github.md) | Integração do GitHub (contas, issues, PRs, notificações, discussões, releases) |
| [scheduler.md](scheduler.md) | Agendador de Tarefas (gerenciamento de trabalhos, histórico de execução) |
| [ratings.md](ratings.md) | Avaliações (definir, batch-set, obter, estatísticas) |
| [favorites.md](favorites.md) | Favoritos (alternar, verificar, listar) |
| [collections.md](collections.md) | Coleções (CRUD, reordenar, batch add/remove, exportação CSV) |
| [tags.md](tags.md) | Tags (batch-set, sugerir) |
| [sns.md](sns.md) | SNS Share & Bluesky Monitor (posting, notificações, triage, auto-response) |
| [hailo-remote-tagger.md](hailo-remote-tagger.md) | Hailo Remote Tagger (config, tagging único/lote, CRUD de tag) |
| [tagger-servers.md](tagger-servers.md) | Registro de Servidor Tagger (cluster distribuído de inferência de tag, gerenciamento de servidor, execução em lote) |
| [svg.md](svg.md) | Rasterização SVG (conversão SVG para PNG/WebP, suporte ao pipeline img2img) |
| [settings.md](settings.md) | Gerenciamento de Configurações (schema, obter/atualizar valores, criptografia de segredo, integração 1Password/Bitwarden) |
| [extensions.md](extensions.md) | Extensões (listar, alternar, config, instalar, segurança, marketplace, autoria) |
| [analysis.md](analysis.md) | Análise de IA (config, análise única/lote, análise de tendência, stats, registro de servidor) |
| [system-update.md](system-update.md) | Atualização do Sistema (verificação de versão, aplicar atualização, gerenciador de atualização unificado) |
| [tools.md](tools.md) | Ferramentas (detecção de duplicatas, computação de hash, busca similar, gerenciamento de cache, backup, limpeza de arquivo, log de debug) |
| [agent.md](agent.md) | Gateway de Segurança do Agente (Kill Switch, Circuit Breaker, Budget, Approval, Scope Fence, Undo, Anomaly Detection) |
| [profiles.md](profiles.md) | Gerenciamento de Perfil (CRUD, duplicata, exportação/importação QR) |
| [wd-tagger.md](wd-tagger.md) | WD-Tagger (auto-tagging Danbooru, gerenciamento de modelo, VLM, XMP) |
| [ocr.md](ocr.md) | OCR (reconhecimento de texto, tradução, suporte a vídeo/PDF, benchmarks, perfis) |
| [apikeys.md](apikeys.md) | Gerenciamento de Chave de API (criar, listar, escopos, revogar) |
| [debug.md](debug.md) | Debug (inspeção de metadados, consulta SQL, verificação de modelo) |
| [ui.md](ui.md) | Gerenciamento de UI (listar, alternar, instalar, desinstalar) |
| [video-analysis.md](video-analysis.md) | Análise de Vídeo (config, status, extração de keyframe) |

## Quick Start (curl)

```bash
# Busca (ambiente sem PIN)
curl "http://localhost:5100/api/search?q=landscape&limit=10"

# Recuperar uma miniatura
curl "http://localhost:5100/api/thumbnail/42" -o thumb.webp

# Busca com API Key
curl -H "Authorization: Bearer sk_your_key_here" \
     "http://localhost:5100/api/search?q=portrait"

# Definir uma avaliação
curl -X POST "http://localhost:5100/api/ratings/set" \
     -H "X-Requested-With: XMLHttpRequest" \
     -H "Content-Type: application/json" \
     -d '{"file_id": 42, "rating": 5}'
```
