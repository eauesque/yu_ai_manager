# API de Busca

APIs para busca de arquivo, sugestões e exibição agrupada.

## GET /api/search

O principal endpoint de busca de arquivo.

### Parâmetros

| Parâmetro | Tipo | Padrão | Descrição |
|-----------|------|---------|-------------|
| `q` | string | `""` | Consulta de busca (texto em prompts, nomes de tag) |
| `sort` | string | `"date"` | Ordem de classificação: `date`, `name`, `size`, `rating`, `random` |
| `order` | string | `"desc"` | `asc` / `desc` |
| `offset` | int | `0` | Posição inicial de paginação |
| `limit` | int | `50` | Número de resultados (máx 200) |
| `cursor` | string | - | Token para paginação baseada em cursor |
| `meta` | string | `"all"` | Tipo de metadados: `all`, `a1111`, `nai`, `comfy`, `unknown` |
| `tags` | string | - | Filtro de tag (separadas por vírgula) |
| `rating_min` | int | - | Classificação mínima (0-5) |
| `rating_max` | int | - | Classificação máxima (0-5) |
| `path` | string | - | Filtro de prefixo de caminho |
| `ext` | string | - | Filtro de extensão (separadas por vírgula, ex: `png,webp`) |
| `has_prompt` | bool | - | Filtrar por presença de prompt |
| `collection_id` | int | - | Buscar dentro de uma coleção |
| `favorites_only` | bool | `false` | Apenas favoritos |
| `group_by` | string | - | Agrupamento: `folder`, `conversation` |

### Resposta

```json
{
  "results": [
    {
      "id": 42,
      "path": "/images/output/00042.png",
      "filename": "00042.png",
      "size": 1234567,
      "mtime": 1709500000,
      "width": 1024,
      "height": 1536,
      "meta_type": "a1111_png",
      "model_name": "animagine-xl-3.1",
      "positive": "1girl, landscape, sunset",
      "negative": "low quality",
      "rating": 4,
      "is_favorite": true,
      "tags": ["landscape", "sunset"]
    }
  ],
  "total": 1500,
  "offset": 0,
  "limit": 50,
  "next_cursor": "eyJtdGltZSI6MTcwOTUwMDAwMCwiaWQiOjQyfQ=="
}
```

## GET /api/search-grouped

Resultados de busca agrupados por pasta/ZIP.

### Parâmetros

Os mesmos parâmetros de consulta que `/api/search`, mais:

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `group_limit` | int | Número máximo de itens mostrados por grupo |

## GET /api/groups-index

Índice de pasta e grupos de contêiner ZIP. Usado para agrupar resultados de busca.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `sort` | string | Ordem de classificação: `name`, `count`, `date` |
| `order` | string | `asc` / `desc` |
| `offset` | int | Posição inicial de paginação |
| `limit` | int | Número de resultados |

## GET /api/group-members

Lista de IDs de arquivo dentro de um contêiner especificado.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `key` | string | Chave de contêiner (caminho de pasta ou caminho ZIP) |

## GET /api/suggest

Autocompletar para tags e prompts.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `q` | string | Texto de entrada |
| `limit` | int | Número de sugestões (padrão 10) |

### Resposta

```json
{
  "suggestions": [
    { "value": "1girl", "count": 5432 },
    { "value": "1boy", "count": 1234 }
  ]
}
```

## GET /api/suggest/lora

Sugestões de nome do modelo LoRA.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `q` | string | Texto de entrada |
| `limit` | int | Número de sugestões |

## GET /api/server-info

Informações básicas do servidor.

### Resposta

```json
{
  "version": "4.12.1",
  "db_path": "/path/to/tags.db",
  "file_count": 150000,
  "tag_count": 8500,
  "auth_required": false,
  "lan_ip": "192.168.1.100",
  "active_ui": "default"
}
```
