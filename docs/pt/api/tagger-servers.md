# API de Registro de Servidor Tagger

API para gerenciar múltiplos workers de inferência de tag (Hailo Remote, ONNX Local, Ryzen AI, etc.) como um cluster unificado, com tagging em lote distribuído via modelo de execução em paralelo com roubo de trabalho de fila compartilhada.

## Visão Geral

O Registro de Servidor Tagger vai além de um único Hailo Remote Tagger ao gerenciar múltiplos backends de inferência heterogêneos como um cluster. Cada servidor tem uma prioridade configurável, e as tarefas são distribuídas de acordo com o modo de distribuição selecionado (single / parallel / idle_first).

### Arquitetura

```
┌─────────────────────────────────────────────────────┐
│                   eauesque Host                      │
│  ┌──────────────────────────────────────────────┐   │
│  │         Tagger Orchestrator                  │   │
│  │  - Shared queue (work-stealing)              │   │
│  │  - Progress aggregation -> JobManager -> SSE │   │
│  └──────────┬──────────────┬──────────────────┘   │
│    ┌────────▼───┐   ┌──────▼────────────┐          │
│    │ Local ONNX │   │ Hailo HTTP Client │          │
│    │ Worker     │   │ Worker            │          │
│    └────────────┘   └──────────┬────────┘          │
└────────────────────────────────│────────────────────┘
              ┌──────────────────┼──────────────────┐
     ┌────────▼───┐    ┌────────▼───┐    ┌────────▼───┐
     │ Pi A       │    │ Pi B       │    │ Future     │
     │ Hailo 10H  │    │ Hailo 10H  │    │ NPU Server │
     └────────────┘    └────────────┘    └────────────┘
```

### Tipos de Servidor

| Tipo | Descrição |
|------|-----------|
| `hailo_remote` | Dispositivo Hailo-10H remoto (ex. Raspberry Pi 5) |
| `onnx_local` | Inferência local de ONNX Runtime |
| `onnx_remote` | Servidor de inferência ONNX remoto |
| `ryzen_ai` | AMD Ryzen AI NPU |

### Modos de Distribuição

| Modo | Descrição |
|------|-----------|
| `single` | Use apenas o servidor habilitado de maior prioridade |
| `parallel` | Executa em todos os servidores habilitados em paralelo (roubo de trabalho) |
| `idle_first` | Prefere servidores inativos primeiro |

---

## Formato de Entrada de Servidor

```json
{
  "id": "pi-hailo-a",
  "name": "Pi5 Hailo A",
  "type": "hailo_remote",
  "priority": 10,
  "enabled": true,
  "config": {
    "endpoint_url": "http://192.168.1.101:8080",
    "bearer_token": "enc:gAAAAABm...",
    "threshold": 0.35,
    "timeout": 30
  }
}
```

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | string | Identificador do servidor (auto-gerado ou especificado manualmente) |
| `name` | string | Nome de exibição |
| `type` | string | Tipo de servidor (`hailo_remote` / `onnx_local` / `onnx_remote` / `ryzen_ai`) |
| `priority` | int | Prioridade (menor = maior prioridade, padrão: 50) |
| `enabled` | bool | Habilitado/desabilitado |
| `config` | object | Configuração específica do tipo (veja abaixo) |

### Campos de config (para servidores remotos)

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|----------|-----------|
| `endpoint_url` | string | Sim | URL do servidor remoto |
| `bearer_token` | string | Não | Token Bearer (auto-criptografado com prefixo `enc:` ao salvar) |
| `threshold` | float | Não | Limite de confiança de tag (padrão: 0.35) |
| `timeout` | int | Não | Timeout de solicitação em segundos (padrão: 30) |

---

## Autenticação

Comunicação com servidores remotos (`hailo_remote` / `onnx_remote`) suporta autenticação de token Bearer opcional.

### Host → Servidor Remoto

Quando `config.bearer_token` está definido, todas as solicitações HTTP (verificações de saúde e tagging) automaticamente incluem um cabeçalho `Authorization: Bearer <token>`. Tokens são armazenados em `config.json` com criptografia Fernet (prefixo `enc:`) e mascarados em respostas de API.

### Lado do Servidor Remoto

`deploy/hailo_tagger_server.py` fornece uma implementação de referência com verificação de token. Defina o token na inicialização através de qualquer um de:

```bash
# Argumento de linha de comando
python hailo_tagger_server.py --token "my-secret-token"

# Ler de arquivo
python hailo_tagger_server.py --token-file /etc/tagger/token

# Variável de ambiente
TAGGER_BEARER_TOKEN=my-secret-token python hailo_tagger_server.py
```

Quando nenhum token está configurado, o servidor opera em modo de acesso aberto (modelo de confiança LAN) para compatibilidade com versões anteriores. Tokens inválidos recebem respostas 401/403.

---

## GET /api/tagger-servers

Lista servidores registrados e o modo de distribuição atual.

### Taxa de Limite

READ (ilimitado)

### Resposta

```json
{
  "ok": true,
  "data": {
    "servers": [
      {
        "id": "pi-hailo-a",
        "name": "Pi5 Hailo A",
        "type": "hailo_remote",
        "priority": 10,
        "enabled": true,
        "config": {
          "endpoint_url": "http://192.168.1.101:8080",
          "threshold": 0.35,
          "timeout": 30
        }
      }
    ],
    "mode": "parallel"
  }
}
```

---

## POST /api/tagger-servers

Adiciona um novo servidor tagger.

### Taxa de Limite

DESTRUCTIVE (~12 req/min, rajada 3)

### Corpo da Solicitação

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|----------|-----------|
| `name` | string | Sim | Nome de exibição |
| `type` | string | Sim | Tipo de servidor |
| `config` | object | Sim | Configuração específica do tipo |
| `priority` | int | Não | Prioridade (padrão: 50) |
| `enabled` | bool | Não | Habilitado/desabilitado (padrão: `true`) |

### Exemplo de Solicitação

```json
{
  "name": "Pi5 Hailo A",
  "type": "hailo_remote",
  "config": {
    "endpoint_url": "http://192.168.1.101:8080",
    "threshold": 0.35,
    "timeout": 30
  },
  "priority": 10
}
```

### Resposta

```json
{
  "ok": true,
  "data": {
    "server": {
      "id": "pi-hailo-a",
      "name": "Pi5 Hailo A",
      "type": "hailo_remote",
      "priority": 10,
      "enabled": true,
      "config": {
        "endpoint_url": "http://192.168.1.101:8080",
        "threshold": 0.35,
        "timeout": 30
      }
    }
  }
}
```

### Erros

| Status | Descrição |
|--------|-----------|
| 400 | Campos obrigatórios ausentes ou tipo inválido |

---

## PUT /api/tagger-servers/{server_id}

Atualiza configurações de um servidor existente. Atualizações parciais suportadas.

### Taxa de Limite

DESTRUCTIVE (~12 req/min, rajada 3)

### Parâmetros de Caminho

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `server_id` | string | ID do servidor alvo |

### Corpo da Solicitação

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|----------|-----------|
| `name` | string | Não | Nome de exibição |
| `type` | string | Não | Tipo de servidor |
| `config` | object | Não | Configuração específica do tipo |
| `priority` | int | Não | Prioridade |
| `enabled` | bool | Não | Habilitado/desabilitado |

### Resposta

```json
{
  "ok": true,
  "data": {
    "server": { "..." }
  }
}
```

### Erros

| Status | Descrição |
|--------|-----------|
| 404 | Servidor não encontrado |

---

## DELETE /api/tagger-servers/{server_id}

Remove um servidor.

### Taxa de Limite

DESTRUCTIVE (~12 req/min, rajada 3)

### Parâmetros de Caminho

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `server_id` | string | ID do servidor alvo |

### Resposta

```json
{
  "ok": true,
  "data": {
    "deleted": "pi-hailo-a"
  }
}
```

### Erros

| Status | Descrição |
|--------|-----------|
| 404 | Servidor não encontrado |

---

## POST /api/tagger-servers/reorder

Reordena prioridades de servidor em lote.

### Taxa de Limite

DESTRUCTIVE (~12 req/min, rajada 3)

### Corpo da Solicitação

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|----------|-----------|
| `order` | string[] | Sim | Array de IDs de servidor em ordem de prioridade |

### Exemplo de Solicitação

```json
{
  "order": ["pi-hailo-a", "local-onnx", "pi-hailo-b"]
}
```

### Resposta

```json
{
  "ok": true,
  "data": {
    "servers": [ "..." ]
  }
}
```

---

## POST /api/tagger-servers/mode

Altera o modo de distribuição.

### Taxa de Limite

DESTRUCTIVE (~12 req/min, rajada 3)

### Corpo da Solicitação

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|----------|-----------|
| `mode` | string | Sim | `single` / `parallel` / `idle_first` |

### Resposta

```json
{
  "ok": true,
  "data": {
    "mode": "parallel"
  }
}
```

### Erros

| Status | Descrição |
|--------|-----------|
| 400 | Valor de modo inválido |

---

## POST /api/tagger-servers/{server_id}/test

Testa conectividade com um servidor específico.

### Taxa de Limite

HEAVY (~20 req/min, rajada 5)

### Parâmetros de Caminho

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `server_id` | string | ID do servidor alvo |

### Resposta (sucesso)

```json
{
  "ok": true,
  "data": {
    "server_id": "pi-hailo-a",
    "reachable": true,
    "latency_ms": 45
  }
}
```

### Resposta (não alcançável)

```json
{
  "ok": true,
  "data": {
    "server_id": "pi-hailo-a",
    "reachable": false,
    "reason": "Connection refused"
  }
}
```

### Erros

| Status | Descrição |
|--------|-----------|
| 404 | Servidor não encontrado |

---

## GET /api/tagger-servers/health

Verificação de saúde de todos os servidores habilitados.

### Taxa de Limite

READ (ilimitado)

### Resposta

```json
{
  "ok": true,
  "data": {
    "results": [
      {
        "server_id": "pi-hailo-a",
        "name": "Pi5 Hailo A",
        "type": "hailo_remote",
        "reachable": true,
        "latency_ms": 45
      },
      {
        "server_id": "local-onnx",
        "name": "Local ONNX",
        "type": "onnx_local",
        "reachable": true,
        "latency_ms": 2
      }
    ]
  }
}
```

---

## POST /api/tagger-servers/batch

Executa tagging em lote distribuído usando o modelo de roubo de trabalho de fila compartilhada. Executa como um trabalho de fundo com progresso reportado via SSE.

### Taxa de Limite

HEAVY (~20 req/min, rajada 5)

### Corpo da Solicitação

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|----------|-----------|
| `file_ids` | int[] | Não | Lista de IDs de arquivo alvo. Auto-seleciona arquivos não marcados se omitido |
| `limit` | int | Não | Máx arquivos para auto-seleção (padrão: 500) |
| `force` | bool | Não | Sobrescreve tags existentes (padrão: `false`) |
| `threshold` | float | Não | Override de limite de confiança de tag (usa configuração por servidor se omitido) |

### Exemplo de Solicitação

```json
{
  "file_ids": [1, 2, 3, 4, 5],
  "force": false,
  "threshold": 0.35
}
```

### Resposta

```json
{
  "ok": true,
  "data": {
    "started": true,
    "job_id": "tagger_servers_batch",
    "total_files": 5,
    "active_servers": ["pi-hailo-a", "local-onnx"]
  }
}
```

### Erros

| Status | Código | Descrição |
|--------|--------|-----------|
| 400 | `no_servers` | Nenhum servidor habilitado disponível |
| 400 | `batch_too_large` | file_ids excede limite |
| 409 | `job_running` | Trabalho de lote já em execução |

---

## POST /api/tagger-servers/batch/cancel

Cancela um trabalho de lote de cluster tagger em execução.

### Resposta

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `status` | string | `"cancelling"` |
| `message` | string | Mensagem de status |

### Códigos de Erro

| Status | Código | Descrição |
|--------|--------|-----------|
| 404 | `job_not_running` | Nenhum trabalho de lote em execução para cancelar |

---

## GET /api/tagger-servers/tags/{file_id}

Recupera tags de tagger para um arquivo.

### Taxa de Limite

READ (ilimitado)

### Parâmetros de Caminho

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `file_id` | int | ID de banco de dados de arquivo alvo |

### Resposta

```json
{
  "ok": true,
  "data": {
    "file_id": 42,
    "tags": [
      {"tag_name": "1girl", "confidence": 0.95, "source": "hailo_remote:pi-hailo-a", "created_at": 1710720000},
      {"tag_name": "solo", "confidence": 0.88, "source": "hailo_remote:pi-hailo-a", "created_at": 1710720000}
    ]
  }
}
```

O campo `source` usa o formato `{type}:{server_id}` (ex. `hailo_remote:pi-hailo-a`, `onnx_local:local-onnx`).

---

## DELETE /api/tagger-servers/tags/{file_id}

Deleta todas as tags de tagger para um arquivo.

### Taxa de Limite

DESTRUCTIVE (~12 req/min, rajada 3)

### Parâmetros de Caminho

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `file_id` | int | ID de banco de dados de arquivo alvo |

### Resposta

```json
{
  "ok": true,
  "data": {
    "file_id": 42,
    "deleted": 15
  }
}
```

---

## GET /api/tagger-servers/stats

Recupera estatísticas de tagger.

### Taxa de Limite

READ (ilimitado)

### Resposta

```json
{
  "ok": true,
  "data": {
    "total_files": 10000,
    "tagged_files": 8500,
    "untagged_files": 1500,
    "servers": {
      "pi-hailo-a": {"tagged": 5000, "type": "hailo_remote"},
      "local-onnx": {"tagged": 3500, "type": "onnx_local"}
    }
  }
}
```

---

## POST /api/tagger-servers/migrate

Migra configuração legada `hailo_tagger` para o formato de Registro de Servidor Tagger. Converte a entrada `hailo_tagger` existente em `config.json` em uma entrada de array `tagger_servers`.

### Taxa de Limite

DESTRUCTIVE (~12 req/min, rajada 3)

### Resposta

```json
{
  "ok": true,
  "data": {
    "migrated": true,
    "server": {
      "id": "legacy-hailo",
      "name": "Hailo Remote (migrated)",
      "type": "hailo_remote",
      "priority": 50,
      "enabled": true,
      "config": {
        "endpoint_url": "http://192.168.1.50:8080",
        "threshold": 0.35,
        "timeout": 30
      }
    }
  }
}
```

### Resposta (nenhuma migração necessária)

```json
{
  "ok": true,
  "data": {
    "migrated": false,
    "reason": "No legacy config found"
  }
}
```

---

## Configuração

Chaves relacionadas em `config.json`:

```json
{
  "tagger_servers": [
    {
      "id": "pi-hailo-a",
      "name": "Pi5 Hailo A",
      "type": "hailo_remote",
      "priority": 10,
      "enabled": true,
      "config": {
        "endpoint_url": "http://192.168.1.101:8080",
        "bearer_token": "enc:gAAAAABm...",
        "threshold": 0.35,
        "timeout": 30
      }
    },
    {
      "id": "local-onnx",
      "name": "Local ONNX",
      "type": "onnx_local",
      "priority": 20,
      "enabled": true,
      "config": {
        "threshold": 0.35
      }
    }
  ],
  "tagger_servers_mode": "parallel"
}
```

| Chave | Tipo | Descrição |
|-------|------|-----------|
| `tagger_servers` | array | Array de entradas de servidor |
| `tagger_servers_mode` | string | Modo de distribuição (`single` / `parallel` / `idle_first`) |

Também pode ser alterado na página de Configurações.

---

## Esquema de DB

Tags são armazenadas na tabela `file_hailo_tags`. A coluna `source` usa o formato `{type}:{server_id}` para identificar qual servidor atribuiu a tag.

```sql
CREATE TABLE file_hailo_tags (
    id         INTEGER PRIMARY KEY,
    file_id    INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    tag_name   TEXT NOT NULL,
    confidence REAL NOT NULL,
    source     TEXT NOT NULL DEFAULT 'hailo_remote',
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    UNIQUE(file_id, tag_name)
);
```

| Coluna | Descrição |
|--------|-----------|
| `file_id` | Chave estrangeira para tabela files |
| `tag_name` | Nome de tag Danbooru (ex. `1girl`, `solo`) |
| `confidence` | Confiança de inferência (0.0-1.0) |
| `source` | Identificador de fonte de tag (formato `{type}:{server_id}`, ex. `hailo_remote:pi-hailo-a`) |
| `created_at` | Timestamp UNIX |
