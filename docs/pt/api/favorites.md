# API de Favoritos

API para adicionar, remover, verificar e listar favoritos.

## POST /api/favorites/toggle

Alternar o status de favorito de um arquivo. Adiciona o arquivo se ainda não está favoritado; remove-o se já presente.

- **Limite de taxa**: WRITE

### Corpo da Requisição

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `file_id` | int | Sim | ID do arquivo de destino (inteiro positivo) |
| `collection_id` | int | Não | ID da coleção (padrão: 1) |

```json
{
  "file_id": 42,
  "collection_id": 1
}
```

### Resposta

```json
{
  "file_id": 42,
  "collection_id": 1,
  "favorited": true
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `file_id` | int | ID do arquivo de destino |
| `collection_id` | int | ID da coleção |
| `favorited` | bool | Estado após alternar. `true` = adicionado, `false` = removido |

## GET /api/favorites/check

Retorna quais dos IDs de arquivo especificados são favoritados.

### Parâmetros

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `ids` | string | Sim | IDs de arquivo separados por vírgula (ex: `1,2,3`) |
| `collection_id` | int | Não | Filtrar para uma coleção específica |

### Resposta

```json
{
  "favorites": [1, 3]
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `favorites` | int[] | Array de IDs de arquivo que são favoritados |

## GET /api/favorites/check_collections

Retorna os IDs de coleção que contêm o arquivo especificado.

### Parâmetros

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `file_id` | int | Sim | ID do arquivo de destino |

### Resposta

```json
{
  "collections": [1, 3]
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `collections` | int[] | Array de IDs de coleção contendo este arquivo |

## GET /api/favorites/list

Recupera uma lista de IDs de arquivo favoritados. Os resultados são classificados por data adicionada em ordem decrescente. Arquivos logicamente deletados são excluídos.

### Parâmetros

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `collection_id` | int | Não | Filtrar para uma coleção específica |

### Resposta

```json
{
  "ids": [42, 55, 67]
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `ids` | int[] | Array de IDs de arquivo favoritados (ordenados por `added_at` DESC) |
