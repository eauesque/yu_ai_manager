# Visão Geral da API

O YU AI Manager fornece uma API REST, e todas as operações da WebUI podem ser executadas programaticamente.
Com mais de 320 endpoints, suporta uma ampla gama de operações, desde gerenciamento de imagens até análise de IA.

> **Dica**: Para convenções detalhadas (autenticação, CSRF, rate limiting, formato de resposta), consulte a seção "Referência da API".

## Autenticação

Suporta 4 métodos de autenticação.

| Método | Uso | Header/Parâmetro |
|------|------|-------------------|
| Autenticação PIN | Sessão do navegador | Login em `/_pin` → cookie de sessão |
| API Key | Comunicação máquina-a-máquina, MCP | `Authorization: Bearer sk_xxxx` |
| Trusted Proxy | Proxy reverso | Header `X-Remote-User` |
| Token LAN Share | Acesso de convidado | Caminho `/s/<token>` |

### Exemplo de Teste com curl

```bash
# Autenticação por API Key (sem necessidade de header CSRF)
curl -H "Authorization: Bearer sk_your_key" \
     http://localhost:5000/api/search?tags=1girl

# Em ambientes com autenticação PIN, 2 etapas são necessárias
# 1. Obter token CSRF
curl -c cookies.txt http://localhost:5000/_pin
# 2. Enviar PIN
curl -b cookies.txt -X POST \
     -H "X-Requested-With: XMLHttpRequest" \
     -d "pin=1234" http://localhost:5000/_pin_check
```

### Proteção CSRF

O header `X-Requested-With` é obrigatório em todos os endpoints `/api/` com POST/PUT/DELETE.
Não é necessário para requisições com API Key Bearer.

## Principais Endpoints

### Pesquisa e Navegação de Imagens

| Método | Caminho | Descrição |
|---------|------|------|
| GET | `/api/search` | Pesquisa com filtros de tags, data, avaliação, etc. |
| GET | `/api/search-grouped` | Pesquisa agrupada por pasta/ZIP |
| GET | `/api/file/<id>` | Obter metadados detalhados da imagem |
| GET | `/api/thumbnail/<id>` | Obter miniatura (WebP, cache ETag) |
| GET | `/api/original/<id>` | Obter imagem original (suporte a requisição Range) |
| GET | `/api/suggest` | Candidatos de autocompletar de tags |

### Avaliações, Tags e Anotações

| Método | Caminho | Descrição |
|---------|------|------|
| POST | `/api/ratings/batch-set` | Definir avaliações em lote |
| POST | `/api/tags/batch-set` | Editar tags em lote |
| POST | `/api/annotations/batch-set` | Definir anotações em lote |
| GET | `/api/annotations/<id>` | Obter anotação |
| GET | `/api/annotations/search` | Pesquisar anotações |

### Coleções

| Método | Caminho | Descrição |
|---------|------|------|
| GET | `/api/collections` | Lista de coleções |
| POST | `/api/collections` | Criar coleção |
| PUT | `/api/collections/<id>` | Renomear coleção |
| DELETE | `/api/collections/<id>` | Excluir coleção |
| POST | `/api/collections/<id>/batch-add` | Adicionar arquivos em lote |
| POST | `/api/collections/<id>/batch-remove` | Remover arquivos em lote |

### Varredura

| Método | Caminho | Descrição |
|---------|------|------|
| POST | `/api/scan/start` | Iniciar varredura |
| GET | `/api/scan/status` | Obter progresso da varredura |
| POST | `/api/scan/cancel` | Cancelar varredura |
| POST | `/api/scan/resume` | Retomar varredura interrompida |
| GET | `/api/scan-roots` | Lista de raízes de varredura |
| POST | `/api/scan-roots` | Adicionar raiz de varredura |

### Análise de IA

| Método | Caminho | Descrição |
|---------|------|------|
| POST | `/api/analysis/analyze/<id>` | Executar análise de IA em imagem |
| GET | `/api/analysis/result/<id>` | Obter resultado de análise |
| POST | `/api/analysis/batch` | Análise em lote |
| POST | `/api/wd-tagger/tag/<id>` | Inferência WD-Tagger |
| POST | `/api/wd-tagger/batch` | Inferência WD-Tagger em lote |
| POST | `/api/analysis/batch/cancel` | Cancelar lote de análise de IA |
| POST | `/api/wd-tagger/batch/cancel` | Cancelar lote WD-Tagger |
| POST | `/api/tagger-servers/batch/cancel` | Cancelar lote do cluster tagger |
| POST | `/api/ocr/<id>` | Executar OCR |

### Configurações

| Método | Caminho | Descrição |
|---------|------|------|
| GET | `/api/settings/schema` | Obter schema de configurações |
| GET | `/api/settings/all` | Obter todos os valores de configuração |
| GET | `/api/settings/<key>` | Obter valor de configuração |
| PUT | `/api/settings/<key>` | Atualizar valor de configuração |

### Gerenciamento de Extensions

| Método | Caminho | Descrição |
|---------|------|------|
| GET | `/api/extensions` | Lista de Extensions |
| POST | `/api/extensions/<name>/toggle` | Habilitar/desabilitar |
| POST | `/api/extensions/install` | Instalar do repositório Git |
| DELETE | `/api/extensions/<name>/uninstall` | Desinstalar |

### Mecanismo de Segurança do Agente

| Método | Caminho | Descrição |
|---------|------|------|
| POST | `/api/agent/kill` | Ativar Kill Switch |
| POST | `/api/agent/resume` | Desativar Kill Switch |
| GET | `/api/agent/status` | Status do mecanismo de segurança |
| GET | `/api/agent/journal` | Journal de operações |
| POST | `/api/agent/undo/<journal_id>` | Desfazer operação |

## Formato de Resposta

Todas as APIs respondem em formato JSON unificado.

```json
{
  "ok": true,
  "data": { ... },
  "error": null
}
```

Em caso de erro:

```json
{
  "ok": false,
  "data": null,
  "error": "Mensagem de erro"
}
```

## Rate Limiting

Sistema de token bucket de 3 tiers.

| Tier | Alvo | Limite | Burst |
|--------|------|------|---------|
| READ | Todas as requisições GET | Ilimitado | - |
| WRITE | POST/PUT/DELETE | ~120 req/min | 30 |
| HEAVY | Busca similar, análise de IA, varredura | ~20 req/min | 5 |
| DESTRUCTIVE | purge, hard-delete, escrita de config | ~12 req/min | 3 |

Quando excedido, HTTP 429 é retornado. Verifique o header `Retry-After` para o número de segundos de espera para retry.

## SSE (Server-Sent Events)

Eventos em tempo real são entregues via SSE de `/api/events/stream`.
Consulte a seção "Eventos SSE" para detalhes.

> **Nota**: Máximo de 10 conexões simultâneas por IP. O limite de tamanho de upload é 100 MB.

## Documentação de Design Interno

Razões detalhadas de decisões de design de API, otimizações de performance SQLite, conhecimentos de design de schema de banco de dados e outros insights de desenvolvimento podem ser visualizados em [MD Viewer](/ext/md-viewer/).
