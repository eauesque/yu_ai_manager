# API de Ferramentas

APIs utilitárias para detecção de duplicatas, computação de hash, pesquisa de imagens similares, gerenciamento de cache, seleção de pasta, backup de DB, limpeza de arquivo e log de depuração.

---

## Duplicatas / Hashes / Varredura

### GET /api/tools/find-duplicates

Detecta arquivos duplicados com base em hash de arquivo ou nome do arquivo.

#### Taxa de Limite

HEAVY

#### Parâmetros

| Parâmetro | Tipo | Padrão | Descrição |
|-----------|------|--------|-----------|
| `cross_directory` | string | `"false"` | Defina como `"true"` para detectar duplicatas em diferentes diretórios |
| `method` | string | `"hash"` | Método de detecção: `"hash"` ou `"name"` |
| `threshold` | int | `5` | Limite de similaridade |

#### Resposta

```json
{
  "groups": [
    {
      "hash": "abc123...",
      "files": [
        { "id": 1, "path": "/images/photo.png", "filename": "photo.png" },
        { "id": 2, "path": "/backup/photo.png", "filename": "photo.png" }
      ]
    }
  ],
  "total_groups": 1,
  "total_duplicates": 2
}
```

### POST /api/tools/compute-hashes

Inicia computação de hash em segundo plano para arquivos sem hashes.

#### Taxa de Limite

HEAVY

#### Solicitação

```json
{
  "type": "both",
  "limit": 5000
}
```

| Parâmetro | Tipo | Padrão | Descrição |
|-----------|------|--------|-----------|
| `type` | string | `"both"` | Tipo de hash: `"md5"`, `"sha256"`, ou `"both"` |
| `limit` | int | `5000` | Número máximo de arquivos a processar |

#### Resposta

```json
{
  "started": true,
  "type": "both",
  "limit": 5000
}
```

### POST /api/tools/delete-duplicates

Deleta arquivos especificados de grupos de duplicatas.

#### Taxa de Limite

DESTRUCTIVE

#### Solicitação

```json
{
  "groups": [
    {
      "keep": 1,
      "delete": [2, 3]
    }
  ],
  "mode": "soft"
}
```

| Parâmetro | Tipo | Padrão | Descrição |
|-----------|------|--------|-----------|
| `groups` | array | Obrigatório | Alvo de exclusão. `keep` = ID de arquivo a manter, `delete` = array de IDs de arquivo a remover |
| `mode` | string | `"soft"` | `"soft"` = exclusão lógica, `"hard"` = exclusão física |

#### Resposta

```json
{
  "deleted": 2,
  "errors": []
}
```

### GET /api/tools/normalize-tags

Normaliza tags (mescla duplicatas, corta espaços em branco, etc.).

#### Parâmetros

| Parâmetro | Tipo | Padrão | Descrição |
|-----------|------|--------|-----------|
| `dry_run` | string | `"false"` | Defina como `"true"` para visualizar alterações sem aplicar |

#### Resposta

```json
{
  "normalized": 15,
  "removed": 3,
  "dry_run": false
}
```

### GET /api/tools/find-similar

Encontra imagens similares a um arquivo especificado (baseado em hash).

#### Taxa de Limite

HEAVY

#### Parâmetros

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `file_id` | int | Sim | ID de arquivo de referência |
| `threshold` | int | Não | Limite de similaridade (1-20, padrão `5`) |

#### Resposta

```json
{
  "file_id": 42,
  "threshold": 5,
  "results": [
    {
      "id": 43,
      "filename": "similar.png",
      "distance": 3
    }
  ],
  "count": 1
}
```

#### Erros

- `400` — `file_id` ausente ou inválido
- `404` — Arquivo especificado não encontrado

### POST /api/tools/scan

Verifica arquivos em um diretório e os registra no banco de dados.

#### Taxa de Limite

HEAVY

#### Solicitação

```json
{
  "path": "/path/to/images",
  "recursive": true,
  "scan_zips": false,
  "compute_hash": false
}
```

| Parâmetro | Tipo | Padrão | Descrição |
|-----------|------|--------|-----------|
| `path` | string | Obrigatório | Caminho do diretório a verificar |
| `recursive` | bool | `true` | Verificar subdiretórios recursivamente |
| `scan_zips` | bool | `false` | Também verificar dentro de arquivos ZIP |
| `compute_hash` | bool | `false` | Computar hashes de arquivo durante varredura |

#### Resposta

```json
{
  "scanned": 150,
  "new": 42,
  "updated": 5,
  "errors": []
}
```

---

## Pesquisa de Arquivo / Inspeção de Metadados

### GET /api/tools/file-search

Pesquisa arquivos no banco de dados por palavra-chave.

#### Parâmetros

| Parâmetro | Tipo | Padrão | Descrição |
|-----------|------|--------|-----------|
| `q` / `query` | string | `""` | Palavra-chave de pesquisa |
| `meta` / `meta_filter` | string | `"all"` | Filtrar por fonte de metadados (`"all"`, `"a1111_png"`, `"novelai_v4_png"`, etc.) |
| `limit` / `n` / `page_size` | int | `100` | Número de resultados (1-500) |

#### Resposta

```json
{
  "results": [
    {
      "id": 1,
      "filename": "image.png",
      "path": "/images/image.png"
    }
  ],
  "count": 1
}
```

### POST /api/inspect

Inspeciona metadados de um arquivo enviado. Extrai metadados sem registrar o arquivo no banco de dados.

#### Taxa de Limite

WRITE

#### Solicitação

`multipart/form-data`:

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|----------|-----------|
| `file` | file | Sim | Arquivo a inspecionar |
| `zip_entry` | string | Não | Caminho dentro do arquivo ZIP (para arquivos ZIP) |

#### Resposta

```json
{
  "filename": "image.png",
  "meta_source": "novelai_v4_png",
  "positive": "1girl, landscape",
  "negative": "bad anatomy",
  "parameters": { ... }
}
```

#### Erros

- `400` — Nenhum arquivo enviado

---

## Seleção de Pasta / Listagem de Diretório

### GET /api/tools/select-folder

Abre o diálogo nativo do seletor de pasta do SO. **Disponível apenas em localhost.**

#### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `initial` / `path` / `dir` | string | Diretório inicial para o diálogo |

#### Resposta

```json
{
  "path": "C:\\Users\\user\\Pictures",
  "cancelled": false
}
```

Quando acessado remotamente:

```json
{
  "path": null,
  "error": "remote_client_no_gui",
  "cancelled": false,
  "message": "Native folder dialog is not available for remote access. Please use the server folder browser."
}
```

### GET /api/tools/list-dirs

Lista diretórios no servidor. **Disponível apenas em localhost.**

#### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `path` / `dir` / `initial` | string | Diretório a listar. Vazio retorna diretórios raiz |

#### Resposta

```json
{
  "current": "C:\\Users",
  "parent": "C:\\",
  "dirs": ["user1", "Public"],
  "roots": ["C:\\", "D:\\"]
}
```

#### Erros

- `403` — Acesso remoto

---

## Gerenciamento de Cache

### GET /api/tools/cache-info

Obtém status do cache de miniatura.

#### Resposta

```json
{
  "count": 1234,
  "size_mb": 56.7
}
```

### POST /api/tools/clear-cache

Limpa todo o cache de miniatura.

#### Taxa de Limite

DESTRUCTIVE

#### Resposta

```json
{
  "cleared": 1234
}
```

### POST /api/tools/rebuild-groups

Força reconstrução do cache de índice de grupos.

#### Taxa de Limite

DESTRUCTIVE

#### Resposta

```json
{
  "status": "rebuilt",
  "folders": 42,
  "zips": 5,
  "file_count": 1500
}
```

### POST /api/tools/faststart-prescan

Pré-gera cache faststart para todos os arquivos MP4/MOV em segundo plano. Retorna 202 imediatamente.

#### Taxa de Limite

WRITE

#### Resposta (202)

```json
{
  "ok": true,
  "started": true,
  "message": "faststart prescan started"
}
```

Quando já em execução (200):

```json
{
  "ok": true,
  "started": false,
  "message": "already running"
}
```

---

## Configurações

### GET /api/settings/config

Obtém a configuração atual mesclada com padrões.

#### Resposta

```json
{
  "port": 5000,
  "pin": "",
  "scan_roots": [],
  "theme": "dark",
  "backup": {
    "enabled": true,
    "periodic_interval_hours": 24
  }
}
```

### POST /api/settings/config

Atualização parcial de configurações. Mesclagem profunda é aplicada a objetos aninhados existentes.

#### Taxa de Limite

DESTRUCTIVE

#### Solicitação

```json
{
  "theme": "light",
  "backup": {
    "enabled": false
  }
}
```

#### Resposta

```json
{
  "status": "saved"
}
```

#### Erros

- `400` — Dados vazios

---

## Backup / Restauração de DB

### GET /api/tools/backup-download

Baixa o arquivo de banco de dados diretamente. **Disponível apenas em localhost.**

#### Resposta

- Content-Type: `application/x-sqlite3`
- Content-Disposition: `attachment; filename="tags_backup_20260322_120000.db"`
- Retorna 404 se banco de dados não encontrado

### POST /api/tools/restore

Restaura o banco de dados enviando um arquivo `.db`. **Disponível apenas em localhost.** Cria automaticamente um backup do banco de dados existente antes de restaurar.

#### Taxa de Limite

WRITE

#### Solicitação

`multipart/form-data`:

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|----------|-----------|
| `file` | file | Sim | Arquivo SQLite com extensão `.db` |

#### Validação

- Verifica bytes mágicos SQLite
- Verifica a tabela `files`
- Rejeita bancos de dados contendo triggers ou views

#### Resposta

```json
{
  "success": true,
  "message": "Database restored successfully",
  "backup": "tags.db.backup_1711100000"
}
```

#### Erros

- `400` — Nenhum arquivo enviado, extensão errada, ou SQLite inválido
- `403` — Acesso remoto
- `500` — Falha de backup ou restauração

### POST /api/tools/backup/create

Cria manualmente um backup gerenciado. **Disponível apenas em localhost.**

#### Taxa de Limite

DESTRUCTIVE

#### Resposta

```json
{
  "success": true,
  "filename": "tags_backup_20260322_120000.db",
  "reason": "manual"
}
```

### GET /api/tools/backup/list

Lista backups disponíveis.

#### Resposta

```json
{
  "backups": [
    {
      "filename": "tags_backup_20260322_120000.db",
      "size": 1048576,
      "created": "2026-03-22T12:00:00"
    }
  ],
  "count": 1
}
```

### POST /api/tools/backup/restore

Restaura banco de dados de um backup nomeado. **Disponível apenas em localhost.**

#### Taxa de Limite

DESTRUCTIVE

#### Solicitação

```json
{
  "filename": "tags_backup_20260322_120000.db"
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `filename` | string | Sim | Nome do arquivo de backup a restaurar |

#### Resposta

```json
{
  "success": true,
  "message": "Backup restored",
  "filename": "tags_backup_20260322_120000.db"
}
```

#### Erros

- `400` — Nome de arquivo ausente ou backup não encontrado
- `403` — Acesso remoto

### POST /api/tools/backup/delete

Deleta um backup específico. **Disponível apenas em localhost.**

#### Taxa de Limite

DESTRUCTIVE

#### Solicitação

```json
{
  "filename": "tags_backup_20260322_120000.db"
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `filename` | string | Sim | Nome do arquivo de backup a deletar |

#### Resposta

```json
{
  "success": true,
  "deleted": "tags_backup_20260322_120000.db"
}
```

### GET /api/tools/backup/status

Obtém o status do sistema de backup.

#### Resposta

```json
{
  "enabled": true,
  "backup_on_scan_complete": true,
  "periodic_interval_hours": 24,
  "max_generations": 5,
  "cooldown_minutes": 5,
  "scheduler_running": true,
  "last_backup_time": "2026-03-22T11:00:00",
  "within_cooldown": false
}
```

---

## Log de Depuração

### GET /api/tools/debug-log

Obtém o final do log de depuração. Retorna `enabled: false` quando modo de depuração está desabilitado.

#### Parâmetros

| Parâmetro | Tipo | Padrão | Descrição |
|-----------|------|--------|-----------|
| `limit` | int | `200` | Número de linhas a recuperar (1-5000) |
| `filter` | string | `""` | String de filtro de linha (correspondência de substring) |

#### Resposta

```json
{
  "enabled": true,
  "lines": ["2026-03-22 12:00:00 [INFO] Server started", "..."],
  "total_lines": 5000,
  "log_path": "/path/to/debug.log",
  "log_size_kb": 128.5
}
```

### GET /api/tools/debug-log/download

Baixa o arquivo de log de depuração. **Disponível apenas em localhost.**

#### Resposta

- Content-Type: `text/plain`
- Content-Disposition: `attachment; filename="debug.log"`

#### Erros

- `400` — Modo de depuração não habilitado
- `403` — Acesso remoto
- `404` — Arquivo de log não encontrado

### POST /api/tools/debug-log/clear

Limpa o log de depuração. **Disponível apenas em localhost.**

#### Taxa de Limite

WRITE

#### Resposta

```json
{
  "success": true,
  "message": "Log cleared"
}
```

#### Erros

- `400` — Modo de depuração não habilitado
- `403` — Acesso remoto
- `404` — Arquivo de log não encontrado

---

## Limpeza de Arquivo

Ferramentas para detectar e limpar duplicatas de arquivo e suas pastas extraídas. Todos os endpoints estão **disponíveis apenas em localhost.**

### POST /api/tools/archive-cleanup/scan

Verifica pares de arquivo-pasta.

#### Taxa de Limite

HEAVY

#### Solicitação

```json
{
  "path": "/path/to/check",
  "recursive": false
}
```

| Parâmetro | Tipo | Padrão | Descrição |
|-----------|------|--------|-----------|
| `path` | string | Obrigatório | Diretório a verificar |
| `recursive` | bool | `false` | Verificar subdiretórios recursivamente |

#### Validação de Caminho

- Caminhos começando com `~` são rejeitados
- Caminhos contendo `..` são rejeitados

#### Resposta

```json
{
  "pairs": [
    {
      "archive_path": "/data/images.zip",
      "folder_path": "/data/images",
      "archive_size": 10485760,
      "folder_size": 12582912,
      "file_count": 42
    }
  ],
  "count": 1
}
```

### POST /api/tools/archive-cleanup/execute

Executa ações de limpeza em pares verificados.

#### Taxa de Limite

DESTRUCTIVE

#### Solicitação

```json
{
  "actions": [
    { "action": "delete_archive", "archive_path": "/data/images.zip" },
    { "action": "delete_folder", "folder_path": "/data/images" },
    { "action": "skip" }
  ]
}
```

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `actions` | array | Array de ações |
| `actions[].action` | string | Um de `"delete_archive"`, `"delete_folder"`, `"skip"` |
| `actions[].archive_path` | string | Obrigatório quando ação é `delete_archive` |
| `actions[].folder_path` | string | Obrigatório quando ação é `delete_folder` |

#### Resposta

```json
{
  "results": [
    { "action": "delete_archive", "success": true },
    { "action": "delete_folder", "success": true },
    { "action": "skip", "success": true }
  ]
}
```

### POST /api/tools/archive-cleanup/llm-verify

Verifica identidade de par arquivo-pasta usando LLM (par único).

#### Taxa de Limite

HEAVY

#### Solicitação

```json
{
  "archive_path": "/data/images.zip",
  "folder_path": "/data/images",
  "pair_info": {
    "archive_size": 10485760,
    "folder_size": 12582912
  }
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `archive_path` | string | Sim | Caminho do arquivo |
| `folder_path` | string | Sim | Caminho da pasta extraída |
| `pair_info` | object | Não | Metadados de par adicionais |

#### Resposta

```json
{
  "verdict": "same",
  "confidence": 0.95,
  "reasoning": "File counts and sizes match exactly."
}
```

### POST /api/tools/archive-cleanup/llm-verify-batch

Verifica em lote múltiplos pares usando LLM. Máximo 50 pares.

#### Taxa de Limite

HEAVY

#### Solicitação

```json
{
  "pairs": [
    {
      "archive_path": "/data/a.zip",
      "folder_path": "/data/a",
      "pair_info": {}
    }
  ]
}
```

| Parâmetro | Tipo | Limite | Descrição |
|-----------|------|--------|-----------|
| `pairs` | array | Máx 50 | Array de pares a verificar |

#### Resposta

```json
{
  "results": [
    { "result": { "verdict": "same", "confidence": 0.95, "reasoning": "..." } }
  ]
}
```

### GET /api/tools/archive-cleanup/llm-config

Obtém configuração LLM de limpeza de arquivo.

#### Resposta

```json
{
  "engine": "ollama",
  "base_url": "http://localhost:11434",
  "model": "llama3",
  "api_key": ""
}
```

### POST /api/tools/archive-cleanup/llm-config

Salva configuração LLM de limpeza de arquivo.

#### Taxa de Limite

WRITE

#### Solicitação

```json
{
  "engine": "ollama",
  "base_url": "http://localhost:11434",
  "model": "llama3"
}
```

#### Resposta

```json
{
  "success": true
}
```

### POST /api/tools/archive-cleanup/list-models

Lista modelos disponíveis para o engine especificado.

#### Solicitação

```json
{
  "engine": "ollama",
  "base_url": "http://localhost:11434"
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `engine` | string | Sim | `"ollama"` ou `"openai_compat"` |
| `base_url` | string | Sim | URL de API do engine |
| `api_key` | string | Não | Chave de API para `openai_compat` |

#### Resposta

```json
{
  "models": ["llama3", "mistral", "codellama"]
}
```

#### Erros

- `400` — Engine inválido ou `base_url` ausente
