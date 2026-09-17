# Debug API

APIs internas para depuração e diagnósticos. Usadas para inspecionar metadados de arquivo, verificar informações do modelo e gerenciar diretórios de raiz varredidos.

Esses endpoints não têm interface de usuário frontend e são principalmente destinados ao desenvolvimento e solução de problemas.

## GET /api/debug/file-meta/<file_id>

Inspecionar metadados detalhados para um arquivo. Retorna metadados armazenados no DB e, para arquivos dentro de archives ZIP, também retorna resultados extraídos recentemente.

### Autenticação

Sessão PIN ou chave API

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `file_id` | int | ID do arquivo (parâmetro de caminho) |

### Resposta

```json
{
  "id": 123,
  "path": "/images/sample.png",
  "meta_source": "a1111_png",
  "parser_version": 5,
  "format": "a1111",
  "model_name": "sd_xl_base_1.0",
  "raw_prompt_length": 256,
  "raw_prompt_preview": "masterpiece, best quality, ...",
  "raw_negative_preview": "lowres, bad anatomy, ...",
  "raw_meta_json_length": 1024,
  "raw_meta_json_preview": "{\"steps\": 20, ...}",
  "has_v4_prompt": false,
  "has_comment": true
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `id` | int | ID do arquivo |
| `path` | string | Caminho do arquivo |
| `meta_source` | string | Fonte de metadados (`a1111_png`, `novelai_v4_png`, etc.) |
| `parser_version` | int | Versão do parser |
| `format` | string | Formato de template |
| `model_name` | string/null | Nome do modelo |
| `raw_prompt_length` | int | Contagem de caracteres do prompt bruto |
| `raw_prompt_preview` | string | Primeiros 300 caracteres do prompt bruto |
| `raw_negative_preview` | string | Primeiros 300 caracteres do prompt negativo |
| `raw_meta_json_length` | int | Contagem de caracteres do JSON de metadados bruto |
| `raw_meta_json_preview` | string | Primeiros 500 caracteres do JSON de metadados bruto |
| `has_v4_prompt` | bool | Se contém um prompt NovelAI V4 |
| `has_comment` | bool | Se contém um campo Comentário |

Para arquivos dentro de archives ZIP, um campo `fresh_extract` é adicionado com resultados de re-extração:

```json
{
  "fresh_extract": {
    "meta_source": "a1111_png",
    "format": "a1111",
    "raw_meta_json_length": 1024,
    "raw_meta_json_preview": "{...}",
    "has_v4_prompt": false,
    "success": true,
    "raw_prompt_preview": "masterpiece, ..."
  }
}
```

### Erros

| Status | Descrição |
|--------|-------------|
| 404 | Arquivo não encontrado |

## GET /api/debug/model-check

Verificar o status de armazenamento de `model_name` na tabela de templates. Retorna estatísticas e amostras para registros com e sem nomes de modelo.

### Autenticação

Sessão PIN ou chave API

### Parâmetros

Nenhum

### Resposta

```json
{
  "total_templates": 1000,
  "with_model_name": 850,
  "without_model_name": 150,
  "samples_with_model": [
    {
      "file_id": 1,
      "model_name": "sd_xl_base_1.0",
      "model_hash": "abc123",
      "format": "a1111"
    }
  ],
  "samples_without_model": [
    {
      "file_id": 42,
      "model_name": null,
      "format": "comfy",
      "raw_meta_json_preview": "{...}"
    }
  ]
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `total_templates` | int | Número total de templates |
| `with_model_name` | int | Número de registros com nome de modelo definido |
| `without_model_name` | int | Número de registros sem nome de modelo |
| `samples_with_model` | array | Amostras com nome de modelo (até 10) |
| `samples_without_model` | array | Amostras sem nome de modelo (até 5) |

## GET /api/scanned-roots

Extrair diretórios raiz de arquivos registrados no DB e retorná-los com contagens de arquivo. Agrega tanto raízes de varredura configuradas quanto raízes de arquivos que não pertencem a nenhuma raiz configurada.

### Autenticação

Sessão PIN ou chave API

### Parâmetros

Nenhum

### Resposta

```json
{
  "roots": [
    {
      "path": "C:\\Images\\AI",
      "count": 5000
    },
    {
      "path": "D:\\Archives",
      "count": 1200
    }
  ]
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `roots` | array | Array de diretórios raiz (ordenado por contagem de arquivo decrescente, máx 50) |
| `roots[].path` | string | Caminho do diretório |
| `roots[].count` | int | Número de arquivos sob este caminho |

### Erros

| Status | Descrição |
|--------|-------------|
| 500 | Falha ao computar resumo de raízes |

## POST /api/debug/query

Executar uma consulta SQL somente leitura. Requer a variável de ambiente `YU_DEBUG_MODE=1` e apenas permite acesso de localhost.

### Limite de Taxa

WRITE

### Autenticação

Sessão PIN ou chave API (somente localhost + `YU_DEBUG_MODE=1`)

### Solicitação

```json
{
  "sql": "SELECT id, path, meta_source FROM files LIMIT 10",
  "limit": 100
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `sql` | string | Sim | Declaração SELECT a executar |
| `limit` | int | Não | Número máximo de linhas a retornar (padrão: 100, máx: 10000) |

### Restrições

- Apenas declarações SELECT são permitidas (INSERT, UPDATE, DELETE, etc. são rejeitadas)
- Múltiplas declarações (separadas por ponto-e-vírgula) não são permitidas
- Consultas contendo palavras-chave de escrita (DROP, ALTER, CREATE, etc.) são rejeitadas

### Resposta

```json
{
  "columns": ["id", "path", "meta_source"],
  "rows": [
    {"id": 1, "path": "/images/test.png", "meta_source": "a1111_png"}
  ],
  "row_count": 1,
  "truncated": false
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `columns` | string[] | Array de nomes de coluna |
| `rows` | object[] | Linhas de resultado (cada linha é um objeto marcado pelo nome da coluna) |
| `row_count` | int | Número de linhas retornadas |
| `truncated` | bool | `true` se resultados foram truncados pelo limite |

### Erros

| Status | Descrição |
|--------|-------------|
| 400 | SQL vazio, múltiplas declarações, consulta não-SELECT, contém operações de escrita, erro de sintaxe SQL |
| 403 | Modo debug não ativado ou acesso de não-localhost |

## POST /api/scanned-roots/purge

Excluir permanentemente todos os registros de arquivo sob o caminho especificado do DB. Registros relacionados (tags, templates, etc.) são excluídos em cascata. Tags não usadas são automaticamente podadas.

### Limite de Taxa

DESTRUCTIVE

### Autenticação

Sessão PIN ou chave API

### Solicitação

```json
{
  "path": "C:\\Images\\OldFolder"
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `path` | string | Sim | Caminho raiz a purgar. Todos os arquivos sob este caminho serão excluídos |

### Resposta

```json
{
  "purged": 150,
  "path": "C:\\Images\\OldFolder"
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `purged` | int | Número de registros de arquivo excluídos |
| `path` | string | O caminho especificado |

### Erros

| Status | Descrição |
|--------|-------------|
| 400 | Caminho não especificado |
| 500 | Operação de purga falhou |
