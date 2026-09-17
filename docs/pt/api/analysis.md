# API de Análise de IA

APIs para análise de imagem alimentada por IA, análise de tendência de prompt e gerenciamento de servidor.

Todos os endpoints POST/PUT/DELETE requerem o header `X-Requested-With` (não obrigatório ao usar API Key de Bearer).

## Limite de Taxa

Os endpoints de escrita sob `/api/analysis/` usam a tier **HEAVY** (~20 req/min, burst 5). Os endpoints GET são ilimitados.

---

## Configuração

### GET /api/analysis/config

Obter a configuração atual de análise de IA. As chaves API são retornadas mascaradas.

#### Resposta

```json
{
  "engine": "ollama",
  "api_key": "sk-T...xy",
  "model": "claude-sonnet-4-6",
  "ollama_url": "http://localhost:11434",
  "ollama_model": "llava:latest",
  "openai_api_key": "sk-...xy",
  "openai_model": "gpt-4o-mini",
  "openai_compat_url": "http://localhost:8080/v1",
  "openai_compat_api_key": "***...ey",
  "openai_compat_model": "qwen2-vl",
  "hailo_vlm_model": "qwen2-vl-2b-instruct",
  "fallback_local_only": false,
  "language": "ja",
  "is_local": true,
  "has_servers": true,
  "servers": [],
  "active_server": "ollama-main"
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `engine` | string | Tipo de engine atual (`claude_api`, `openai`, `ollama`, `openai_compat`, `hailo_vlm`) |
| `api_key` | string | Chave API do Claude (mascarada) |
| `model` | string | Nome do modelo Claude API |
| `ollama_url` | string | URL do servidor Ollama |
| `ollama_model` | string | Nome do modelo Ollama |
| `openai_api_key` | string | Chave API do OpenAI (mascarada) |
| `openai_model` | string | Nome do modelo OpenAI |
| `openai_compat_url` | string | URL do servidor compatível com OpenAI |
| `openai_compat_api_key` | string | Chave API compatível com OpenAI (mascarada) |
| `openai_compat_model` | string | Nome do modelo compatível com OpenAI |
| `hailo_vlm_model` | string | Nome do modelo VLM do Hailo |
| `fallback_local_only` | boolean | Se deve restringir apenas a engines locais |
| `language` | string | Idioma para resultados de análise (`ja`, `en`, etc.) |
| `is_local` | boolean | Se o engine atual é local (gratuito) |
| `has_servers` | boolean | Se o registro de servidor está configurado |
| `servers` | array | Lista de servidores (apenas quando `has_servers` é true) |
| `active_server` | string | ID do servidor ativo (apenas quando `has_servers` é true) |

### POST /api/analysis/config

Salvar configuração de análise de IA. Valores mascarados (strings contendo `...`) não são sobrescritos. As chaves API são criptografadas automaticamente.

#### Limite de Taxa

HEAVY

#### Solicitação

```json
{
  "engine": "ollama",
  "ollama_url": "http://localhost:11434",
  "ollama_model": "llava:latest",
  "language": "ja"
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `engine` | string | Não | Tipo de engine |
| `api_key` | string | Não | Chave API do Claude |
| `model` | string | Não | Modelo Claude API |
| `ollama_url` | string | Não | URL do servidor Ollama |
| `ollama_model` | string | Não | Nome do modelo Ollama |
| `openai_api_key` | string | Não | Chave API do OpenAI |
| `openai_model` | string | Não | Nome do modelo OpenAI |
| `openai_compat_url` | string | Não | URL do servidor compatível com OpenAI |
| `openai_compat_api_key` | string | Não | Chave API compatível com OpenAI |
| `openai_compat_model` | string | Não | Nome do modelo compatível com OpenAI |
| `hailo_vlm_model` | string | Não | Nome do modelo VLM do Hailo |
| `fallback_local_only` | boolean | Não | Restringir apenas a engines locais |
| `language` | string | Não | Idioma para resultados de análise |

#### Resposta

```json
{
  "success": true
}
```

---

## Descoberta de Engine

### GET /api/analysis/available-engines

Obter uma lista de engines configurados e acessíveis. Os engines da nuvem são excluídos quando `fallback_local_only` está ativado.

#### Resposta

```json
{
  "engines": [
    {
      "type": "ollama",
      "label": "Ollama",
      "model": "llava:latest",
      "models": ["llava:latest", "llava:13b", "bakllava:latest"]
    },
    {
      "type": "hailo_vlm",
      "label": "Hailo VLM",
      "model": "qwen2-vl-2b-instruct",
      "models": ["qwen2-vl-2b-instruct"]
    }
  ]
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `engines[].type` | string | Identificador de tipo de engine |
| `engines[].label` | string | Rótulo de exibição |
| `engines[].model` | string | Modelo configurado atualmente |
| `engines[].models` | string[] | Lista de modelos disponíveis |

---

## Análise de Arquivo Único

### POST /api/analysis/analyze/<file_id>

Analisar um único arquivo com um engine de IA. Suporta imagens, vídeos e imagens dentro de archives.

#### Limite de Taxa

HEAVY

#### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `file_id` | int | ID do arquivo (parâmetro de caminho) |

#### Solicitação

O corpo JSON é opcional. Quando omitido, configurações padrão são usadas.

```json
{
  "mode": "full",
  "engine": "ollama",
  "model": "llava:latest",
  "server_id": "ollama-main"
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `mode` | string | Não | Modo de análise. Padrão `"full"` |
| `engine` | string | Não | Engine tipo sobrescrita |
| `model` | string | Não | Nome do modelo sobrescrita |
| `server_id` | string | Não | Especificar ID do servidor a usar |

#### Resposta (200)

```json
{
  "success": true,
  "result": {
    "description": "A landscape painting with mountains...",
    "style": "digital art",
    "quality_score": 8,
    "tags": ["landscape", "mountains", "sunset"]
  },
  "engine": "Ollama (llava:latest)"
}
```

#### Respostas de Erro

- `400`: Engine não configurado / engine inválido especificado
- `404`: Arquivo não encontrado / arquivo não existe no disco
- `500`: Erro durante análise

### GET /api/analysis/result/<file_id>

Recuperar resultados de análise armazenados para um arquivo. Retorna todos os resultados quando múltiplos engines/modos foram usados.

#### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `file_id` | int | ID do arquivo (parâmetro de caminho) |

#### Resposta (200) -- Resultados Encontrados

```json
{
  "found": true,
  "result": {
    "engine": "Ollama (llava:latest)",
    "description": "A landscape painting...",
    "style": "digital art",
    "quality_score": 8,
    "analyzed_at": 1709500000
  },
  "results": [
    {
      "engine": "Ollama (llava:latest)",
      "description": "A landscape painting...",
      "style": "digital art",
      "quality_score": 8,
      "analyzed_at": 1709500000
    }
  ]
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `found` | boolean | Se resultados de análise existem |
| `result` | object | Resultado de análise mais recente (compatibilidade com versões anteriores) |
| `results` | array | Array de todos os resultados de análise |

#### Resposta (200) -- Sem Resultados

```json
{
  "found": false
}
```

---

## Análise em Lote

### POST /api/analysis/batch

Iniciar um trabalho de análise de IA em lote em arquivos não analisados. Executa em segundo plano.

#### Limite de Taxa

HEAVY

#### Solicitação

```json
{
  "limit": 10,
  "scan_root": "",
  "file_ids": [],
  "server_ids": ["ollama-main", "openai-compat"]
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `limit` | int | Não | Número máximo de arquivos a analisar. Padrão 10. Limitado a 10 para cloud engines. 0 significa todos os arquivos para engines locais |
| `scan_root` | string | Não | Restringir alvos a uma raiz de varredura específica |
| `file_ids` | int[] | Não | Especificar diretamente IDs de arquivo a analisar |
| `server_ids` | string[] | Não | IDs de servidor a usar. Múltiplos servidores habilitam análise paralela |

#### Resposta (200)

```json
{
  "started": true,
  "count": 10,
  "parallel": false
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `started` | boolean | Se o trabalho foi iniciado |
| `count` | int | Número de arquivos a analisar |
| `parallel` | boolean | Se executando em paralelo (múltiplos `server_ids`) |
| `worker` | boolean | True se despachado via inference worker |
| `subprocess` | boolean | True se executando em subprocess (Hailo VLM) |

#### Respostas de Erro

- `400`: Sem arquivos para analisar
- `409`: Trabalho de análise de IA já em execução

### POST /api/analysis/batch/cancel

Cancelar um trabalho de análise de IA em lote em execução.

#### Limite de Taxa

HEAVY

#### Solicitação

Nenhum corpo obrigatório.

#### Resposta (200)

```json
{
  "status": "cancelling",
  "message": "AI analysis cancel requested"
}
```

#### Respostas de Erro

- `404`: Nenhum trabalho de análise de IA em execução

---

## Análise de Tendência de Prompt

### POST /api/analysis/trends

Executar análise de tendência nos 50 prompts mais recentes. Os resultados são salvos automaticamente no histórico.

#### Limite de Taxa

HEAVY

#### Solicitação

Nenhum corpo obrigatório.

#### Resposta (200)

```json
{
  "success": true,
  "result": {
    "summary": "Recent prompts focus on landscape and character art...",
    "top_themes": ["landscape", "character", "fantasy"],
    "trend_direction": "increasing variety"
  }
}
```

#### Respostas de Erro

- `400`: Chave API não configurada (ao usar cloud engines)
- `500`: Erro durante análise de tendência

### GET /api/analysis/trends/history

Obter histórico de análise de tendência de prompt. Ordenado mais recente primeiro. Máximo 50 entradas retidas.

#### Parâmetros

| Parâmetro | Tipo | Padrão | Descrição |
|-----------|------|---------|-------------|
| `limit` | int | 20 | Número de entradas a buscar (máx 50) |
| `offset` | int | 0 | Offset |

#### Resposta

```json
{
  "items": [
    {
      "id": 5,
      "engine": "ollama",
      "analyzed_at": 1709500000,
      "prompt_count": 50,
      "result": {
        "summary": "Recent prompts focus on...",
        "top_themes": ["landscape", "character"]
      }
    }
  ]
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `items[].id` | int | ID de entrada do histórico |
| `items[].engine` | string | Tipo de engine usado |
| `items[].analyzed_at` | int | Timestamp UNIX da análise |
| `items[].prompt_count` | int | Número de prompts analisados |
| `items[].result` | object | Resultado de análise de tendência |

### DELETE /api/analysis/trends/history/<history_id>

Excluir uma única entrada de histórico de análise de tendência.

#### Limite de Taxa

HEAVY

#### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `history_id` | int | ID de entrada do histórico (parâmetro de caminho) |

#### Resposta

```json
{
  "deleted": true
}
```

#### Respostas de Erro

- `404`: Entrada de histórico não encontrada

---

## Estatísticas

### GET /api/analysis/stats

Obter estatísticas de análise de IA.

#### Resposta

```json
{
  "total_analyzed": 150,
  "total_files": 1200,
  "styles": [
    { "style": "digital art", "count": 45 },
    { "style": "anime", "count": 30 }
  ],
  "quality_distribution": [
    { "tier": "excellent", "count": 20, "avg_score": 8.5 },
    { "tier": "good", "count": 60, "avg_score": 6.8 },
    { "tier": "average", "count": 50, "avg_score": 4.9 },
    { "tier": "low", "count": 20, "avg_score": 2.3 }
  ]
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `total_analyzed` | int | Número de arquivos analisados |
| `total_files` | int | Número total de arquivos (excluindo excluídos) |
| `styles` | array | Divisão de estilo (top 10) |
| `styles[].style` | string | Nome de estilo |
| `styles[].count` | int | Número de arquivos |
| `quality_distribution` | array | Distribuição de pontuação de qualidade |
| `quality_distribution[].tier` | string | Tier de qualidade (`excellent` >= 8, `good` >= 6, `average` >= 4, `low` < 4) |
| `quality_distribution[].count` | int | Número de arquivos |
| `quality_distribution[].avg_score` | float | Pontuação média |

---

## Conexão Ollama

### GET /api/analysis/ollama/models

Conectar ao servidor Ollama configurado e listar modelos disponíveis.

#### Resposta

```json
{
  "available": true,
  "models": [
    { "name": "llava:latest", "size": 4700000000 }
  ]
}
```

#### Respostas de Erro

- `400`: URL de Ollama inválida

### POST /api/analysis/ollama/test

Testar conexão com um servidor Ollama na URL especificada.

#### Limite de Taxa

HEAVY

#### Solicitação

```json
{
  "ollama_url": "http://localhost:11434"
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `ollama_url` | string | Sim | URL do servidor Ollama a testar |

#### Resposta

```json
{
  "available": true,
  "models": [
    { "name": "llava:latest", "size": 4700000000 }
  ]
}
```

#### Respostas de Erro

- `400`: URL está vazia / URL é inválida

---

## Conexão com Servidor Compatível com OpenAI

### GET /api/analysis/openai-compat/models

Conectar ao servidor compatível com OpenAI configurado e listar modelos disponíveis.

#### Resposta

```json
{
  "available": true,
  "models": [
    { "id": "qwen2-vl-7b-instruct" }
  ]
}
```

#### Respostas de Erro

- `400`: URL não configurada / URL é inválida

### POST /api/analysis/openai-compat/test

Testar conexão com um servidor compatível com OpenAI na URL especificada.

#### Limite de Taxa

HEAVY

#### Solicitação

```json
{
  "url": "http://localhost:8080/v1",
  "api_key": "optional-key"
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `url` | string | Sim | URL a testar |
| `api_key` | string | Não | Chave API (se obrigatória) |

#### Resposta

```json
{
  "available": true,
  "models": [
    { "id": "qwen2-vl-7b-instruct" }
  ]
}
```

#### Respostas de Erro

- `400`: URL está vazia / URL é inválida

---

## Registro de Servidor de IA

Registrar e gerenciar múltiplos servidores de IA com fallback baseado em prioridade e análise paralela.

### GET /api/analysis/servers

Listar todos os servidores registrados com status. As chaves API são mascaradas.

#### Resposta

```json
{
  "servers": [
    {
      "id": "ollama-main",
      "name": "Ollama (llava:latest)",
      "type": "ollama",
      "priority": 10,
      "enabled": true,
      "config": {
        "base_url": "http://localhost:11434",
        "model": "llava:latest"
      },
      "is_active": true,
      "status": "unknown"
    }
  ]
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `servers[].id` | string | ID do servidor (imutável) |
| `servers[].name` | string | Nome de exibição |
| `servers[].type` | string | Tipo de engine (`claude_api`, `openai`, `ollama`, `openai_compat`, `hailo_vlm`) |
| `servers[].priority` | int | Prioridade (menor = prioridade maior) |
| `servers[].enabled` | boolean | Ativado/desativado |
| `servers[].config` | object | Configuração específica do engine |
| `servers[].is_active` | boolean | Se este é o servidor ativo atualmente |
| `servers[].status` | string | Status de conexão (sempre `"unknown"` na visualização em lista) |

### POST /api/analysis/servers

Registrar um novo servidor. O primeiro servidor é automaticamente definido como ativo.

#### Limite de Taxa

HEAVY

#### Solicitação

```json
{
  "name": "Local Ollama",
  "type": "ollama",
  "config": {
    "base_url": "http://localhost:11434",
    "model": "llava:latest"
  }
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `name` | string | Sim | Nome do servidor |
| `type` | string | Sim | Tipo de engine |
| `config` | object | Sim | Configuração específica do engine |
| `priority` | int | Não | Prioridade |
| `enabled` | boolean | Não | Ativado/desativado. Padrão true |

#### Resposta (201)

```json
{
  "success": true,
  "server": {
    "id": "local-ollama",
    "name": "Local Ollama",
    "type": "ollama",
    "priority": 10,
    "enabled": true,
    "config": { "base_url": "http://localhost:11434", "model": "llava:latest" }
  }
}
```

#### Respostas de Erro

- `400`: Erro de validação / limite de servidor atingido

### PUT /api/analysis/servers/<server_id>

Atualizar configurações de um servidor. O campo `id` não pode ser alterado.

#### Limite de Taxa

HEAVY

#### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `server_id` | string | ID do servidor (parâmetro de caminho) |

#### Solicitação

```json
{
  "name": "Updated Name",
  "type": "ollama",
  "priority": 20,
  "enabled": true,
  "config": { "base_url": "http://192.168.1.100:11434", "model": "llava:13b" }
}
```

Todos os campos são opcionais. Apenas campos especificados são atualizados.

#### Resposta

```json
{
  "success": true,
  "server": { "id": "ollama-main", "name": "Updated Name", "..." : "..." }
}
```

#### Respostas de Erro

- `400`: Tipo inválido / servidor não encontrado

### DELETE /api/analysis/servers/<server_id>

Excluir um servidor. Se o servidor ativo for excluído, o próximo servidor de prioridade mais alta fica ativo automaticamente.

#### Limite de Taxa

HEAVY

#### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `server_id` | string | ID do servidor (parâmetro de caminho) |

#### Resposta

```json
{
  "success": true
}
```

#### Respostas de Erro

- `400`: Servidor não encontrado

### POST /api/analysis/servers/<server_id>/activate

Alternar o servidor ativo.

#### Limite de Taxa

HEAVY

#### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `server_id` | string | ID do servidor (parâmetro de caminho) |

#### Resposta

```json
{
  "success": true,
  "active": "ollama-main"
}
```

#### Respostas de Erro

- `400`: Servidor não encontrado

### POST /api/analysis/servers/<server_id>/test

Executar um teste de conectividade em um servidor. O tempo de resposta também é medido.

#### Limite de Taxa

HEAVY

#### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `server_id` | string | ID do servidor (parâmetro de caminho) |

#### Resposta

```json
{
  "success": true,
  "available": true,
  "elapsed_ms": 45,
  "server": {
    "id": "ollama-main",
    "name": "Local Ollama",
    "type": "ollama",
    "config": { "..." : "..." }
  }
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `available` | boolean | Se o servidor está acessível |
| `elapsed_ms` | int | Tempo de resposta do teste de conexão em milissegundos |
| `server` | object | Informações do servidor |

#### Respostas de Erro

- `400`: Servidor não encontrado

### PUT /api/analysis/servers/reorder

Atualizar em lote as prioridades do servidor.

#### Limite de Taxa

HEAVY

#### Solicitação

```json
{
  "server_ids": ["ollama-main", "openai-compat", "claude-api"]
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `server_ids` | string[] | Sim | Array de IDs do servidor. A ordem especificada se torna a nova ordem de prioridade |

#### Resposta

```json
{
  "success": true
}
```

#### Respostas de Erro

- `400`: `server_ids` não é um array

### POST /api/analysis/servers/migrate

Auto-migração do config legado `ai_analysis` para o novo formato de registro de servidor. Falha se servidores já existirem.

#### Limite de Taxa

HEAVY

#### Solicitação

Nenhum corpo obrigatório.

#### Resposta

```json
{
  "success": true,
  "servers": [
    { "id": "ollama", "name": "Ollama (llava:latest)", "type": "ollama", "..." : "..." }
  ],
  "migrated": 3
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `servers` | array | Servidores criados pela migração |
| `migrated` | int | Número de servidores criados |

#### Respostas de Erro

- `400`: `ai_servers` já existe
