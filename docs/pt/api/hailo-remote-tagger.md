# API Hailo Remote Tagger

API para enviar imagens a um servidor de inferência remoto Hailo AI HAT (ex. Raspberry Pi 5) na rede, executar inferência de tag Danbooru e salvar resultados no banco de dados.

## Visão Geral

Mesmo sem uma GPU local ou runtime ONNX, você pode usar um dispositivo Hailo-10H em sua LAN como um tagger remoto. Imagens são enviadas como multipart/form-data, e JSON de tag é retornado como uma resposta.

---

## GET /api/hailo-tagger/config

Recupera configuração atual.

### Taxa de Limite

READ (ilimitado)

### Resposta

```json
{
  "ok": true,
  "data": {
    "config": {
      "enabled": false,
      "endpoint_url": "",
      "threshold": 0.35,
      "timeout": 30
    }
  }
}
```

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `enabled` | bool | Se Hailo Remote Tagger está habilitado |
| `endpoint_url` | string | URL do endpoint Pi (ex. `http://192.168.1.50:8080`) |
| `threshold` | float | Limite de confiança de tag (apenas tags acima disso são salvas) |
| `timeout` | int | Timeout de solicitação em segundos |

---

## POST /api/hailo-tagger/config

Salva configuração. Atualizações parciais suportadas (apenas campos especificados são alterados).

### Taxa de Limite

DESTRUCTIVE (~12 req/min, rajada 3)

### Corpo da Solicitação

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|----------|-----------|
| `enabled` | bool | Não | Habilitar/desabilitar |
| `endpoint_url` | string | Não | URL do endpoint Pi |
| `threshold` | float | Não | Limite de confiança de tag |
| `timeout` | int | Não | Timeout de solicitação (segundos) |

### Exemplo de Solicitação

```json
{
  "enabled": true,
  "endpoint_url": "http://192.168.1.50:8080",
  "threshold": 0.35
}
```

### Resposta

```json
{
  "ok": true,
  "data": {
    "config": {
      "enabled": true,
      "endpoint_url": "http://192.168.1.50:8080",
      "threshold": 0.35,
      "timeout": 30
    }
  }
}
```

### Erros

| Status | Descrição |
|--------|-----------|
| 400 | Objeto JSON inválido |

---

## GET /api/hailo-tagger/status

Testa conexão com o endpoint Hailo. Envia uma solicitação GET para o endpoint `/health` para verificar acessibilidade.

### Taxa de Limite

READ (ilimitado)

### Resposta (sucesso)

```json
{
  "ok": true,
  "data": {
    "enabled": true,
    "reachable": true,
    "endpoint_url": "http://192.168.1.50:8080"
  }
}
```

### Resposta (não configurado / não alcançável)

```json
{
  "ok": true,
  "data": {
    "enabled": true,
    "reachable": false,
    "reason": "Connection refused",
    "endpoint_url": "http://192.168.1.50:8080"
  }
}
```

---

## POST /api/hailo-tagger/tag/{file_id}

Marca um único arquivo.

### Taxa de Limite

HEAVY (~20 req/min, rajada 5)

### Parâmetros de Caminho

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `file_id` | int | ID de banco de dados de arquivo alvo |

### Corpo da Solicitação

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|----------|-----------|
| `force` | bool | Não | Sobrescreve tags existentes (padrão: `false`) |

### Resposta

```json
{
  "ok": true,
  "data": {
    "file_id": 42,
    "filepath": "/images/test.png",
    "tag_count": 15,
    "tags": [
      {"tag": "1girl", "confidence": 0.95},
      {"tag": "solo", "confidence": 0.88}
    ]
  }
}
```

### Erros

| Status | Código | Descrição |
|--------|--------|-----------|
| 400 | `disabled` | Hailo Tagger está desabilitado |
| 400 | `not_configured` | URL do endpoint não configurada |
| 400 | `file_not_found` | Arquivo não encontrado no banco de dados |
| 400 | `file_missing` | Arquivo não existe no disco |
| 400 | `unsupported_type` | Tipo de arquivo não suportado para tagging |
| 502 | `request_failed` | Falha ao conectar com servidor remoto |

---

## POST /api/hailo-tagger/batch

Marca múltiplos arquivos em lote. Executa como um trabalho de fundo.

### Taxa de Limite

HEAVY (~20 req/min, rajada 5)

### Corpo da Solicitação

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|----------|-----------|
| `file_ids` | int[] | Não | Lista de IDs de arquivo alvo (máx 500). Auto-seleciona arquivos não marcados se omitido |
| `limit` | int | Não | Máx arquivos para auto-seleção (padrão: 100) |
| `force` | bool | Não | Sobrescreve tags existentes (padrão: `false`) |

### Exemplo de Solicitação

```json
{
  "file_ids": [1, 2, 3, 4, 5],
  "force": false
}
```

### Resposta

```json
{
  "ok": true,
  "data": {
    "started": true,
    "job_id": "hailo_tagger"
  }
}
```

### Erros

| Status | Código | Descrição |
|--------|--------|-----------|
| 400 | `batch_too_large` | file_ids excede 500 |
| 409 | `job_running` | Trabalho em lote já em execução |

---

## GET /api/hailo-tagger/tags/{file_id}

Recupera tags Hailo para um arquivo.

### Taxa de Limite

READ (ilimitado)

### Resposta

```json
{
  "ok": true,
  "data": {
    "file_id": 42,
    "tags": [
      {"tag_name": "1girl", "confidence": 0.95, "source": "hailo_remote", "created_at": 1710720000},
      {"tag_name": "solo", "confidence": 0.88, "source": "hailo_remote", "created_at": 1710720000}
    ]
  }
}
```

---

## DELETE /api/hailo-tagger/tags/{file_id}

Deleta todas as tags Hailo para um arquivo.

### Taxa de Limite

DESTRUCTIVE (~12 req/min, rajada 3)

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

## Esquema de DB

Tags Hailo são armazenadas em uma tabela dedicada `file_hailo_tags` (independente de `file_wd_tags`).

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
| `source` | Identificador de fonte de tag (`hailo_remote` ou `hailo_remote:<server_id>` ao usar o registro) |
| `created_at` | Timestamp UNIX |

---

## Configuração

Seção `hailo_tagger` em `config.json`:

```json
{
  "hailo_tagger": {
    "enabled": true,
    "endpoint_url": "http://192.168.1.50:8080",
    "threshold": 0.35,
    "timeout": 30
  }
}
```

Também pode ser alterada na página de Configurações.

> **Nota**: Para gerenciar múltiplos servidores tagger, use a [API de Registro de Servidor Tagger](tagger-servers.md). Configuração legada pode ser auto-migrada via `/api/tagger-servers/migrate`. O Registro de Servidor Tagger também suporta autenticação de token Bearer.
