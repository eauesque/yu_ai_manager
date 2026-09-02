# API de Coleções

APIs para gerenciar coleções (grupos de favoritos).

## GET /api/collections

Listar todas as coleções. Ordenadas por `sort_order` ASC, depois `id` ASC.

### Parâmetros

Nenhum

### Resposta

```json
{
  "collections": [
    {
      "id": 1,
      "name": "Favorites",
      "sort_order": 0,
      "created_at": 1709500000,
      "count": 42,
      "is_smart": false,
      "query_json": null
    }
  ]
}
```

## POST /api/collections

Criar uma nova coleção.

### Limite de Taxa

WRITE

### Requisição

```json
{
  "name": "My Collection",
  "query_json": null
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `name` | string | Sim | Nome da coleção |
| `query_json` | object/null | Não | Consulta para coleções inteligentes. Omita para coleções regulares |

### Resposta (201)

```json
{
  "id": 2,
  "name": "My Collection",
  "is_smart": false
}
```

## PUT /api/collections/<id>

Renomear uma coleção.

### Limite de Taxa

WRITE

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `id` | int | ID da coleção (parâmetro de caminho) |

### Requisição

```json
{
  "name": "Renamed Collection"
}
```

### Resposta

```json
{
  "id": 2,
  "name": "Renamed Collection"
}
```

## DELETE /api/collections/<id>

Deletar uma coleção. Todas as entradas de favoritos na coleção também são deletadas.

A coleção padrão (`id=1`) não pode ser deletada.

### Limite de Taxa

WRITE

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `id` | int | ID da coleção (parâmetro de caminho) |

### Resposta

```json
{
  "deleted": 2
}
```

## POST /api/collections/reorder

Alterar a ordem de exibição das coleções.

### Limite de Taxa

WRITE

### Requisição

```json
{
  "ids": [3, 1, 2]
}
```

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `ids` | int[] | Array de IDs de coleção. A ordem especificada se torna a nova ordem de classificação |

### Resposta

```json
{
  "ok": true
}
```

## POST /api/collections/<id>/batch-add

Adicionar arquivos a uma coleção em lote. Idempotente: entradas que já existem são ignoradas e contadas como sucessos.

### Limite de Taxa

WRITE

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `id` | int | ID da coleção (parâmetro de caminho) |

### Requisição

```json
{
  "file_ids": [1, 2, 3]
}
```

| Parâmetro | Tipo | Limite | Descrição |
|-----------|------|-------|-------------|
| `file_ids` | int[] | Max 500 | Array de IDs de arquivo a adicionar |

### Resposta

```json
{
  "total": 3,
  "succeeded": 3,
  "failed": 0,
  "errors": []
}
```

## POST /api/collections/<id>/batch-remove

Remover arquivos de uma coleção em lote.

### Limite de Taxa

WRITE

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `id` | int | ID da coleção (parâmetro de caminho) |

### Requisição

```json
{
  "file_ids": [1, 2]
}
```

| Parâmetro | Tipo | Limite | Descrição |
|-----------|------|-------|-------------|
| `file_ids` | int[] | Max 500 | Array de IDs de arquivo a remover |

### Resposta

```json
{
  "total": 2,
  "succeeded": 2,
  "failed": 0,
  "errors": []
}
```

## GET /api/collections/<id>/export/csv

Exportar arquivos em uma coleção como CSV.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `id` | int | ID da coleção (parâmetro de caminho) |

### Resposta

- Content-Type: `text/csv; charset=utf-8`
- Colunas CSV: `id`, `filename`, `folder`, `path`, `meta_source`, `mtime`, `positive`, `negative`
- Retorna 404 se coleção não encontrada
