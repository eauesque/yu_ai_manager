# API de Avaliações

API para gerenciar avaliações de arquivos (avaliações de 1 a 5 estrelas): definir, recuperar e exibir estatísticas.

## POST /api/ratings/set

Definir uma avaliação para um arquivo. Especifique `rating=0` para limpar a avaliação.

**Limite de taxa**: WRITE

### Requisição

```json
{
  "file_id": 42,
  "rating": 5
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `file_id` | int | Sim | ID do arquivo (inteiro positivo) |
| `rating` | int | Sim | Valor da avaliação (0–5). 0 limpa a avaliação |

### Resposta

```json
{
  "file_id": 42,
  "rating": 5
}
```

## POST /api/ratings/batch-set

Definir avaliações para múltiplos arquivos de uma vez.

**Limite de taxa**: WRITE

### Requisição

```json
{
  "items": [
    { "file_id": 1, "rating": 5 },
    { "file_id": 2, "rating": 3 }
  ]
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `items` | array | Sim | Lista de entradas de avaliação (máx 500) |
| `items[].file_id` | int | Sim | ID do arquivo (inteiro positivo) |
| `items[].rating` | int | Sim | Valor da avaliação (0–5) |

### Resposta

```json
{
  "total": 2,
  "succeeded": 2,
  "failed": 0,
  "errors": []
}
```

## GET /api/ratings/get

Obter a avaliação de um arquivo. Retorna `rating: 0` se o arquivo não tiver classificação.

### Parâmetros

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `file_id` | int | Sim | ID do arquivo (parâmetro de query) |

### Resposta

```json
{
  "file_id": 42,
  "rating": 5
}
```

> **Nota**: Arquivos sem classificação retornam `rating: 0`.

## POST /api/ratings/batch

Recuperar avaliações para múltiplos arquivos de uma vez.

### Requisição

```json
{
  "file_ids": [1, 2, 3]
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `file_ids` | array | Sim | Lista de IDs de arquivo |

### Resposta

```json
{
  "ratings": {
    "1": 5,
    "3": 4
  }
}
```

> **Nota**: Apenas arquivos com classificação aparecem no mapa. Arquivos sem classificação são omitidos da resposta.

## GET /api/ratings/stats

Obter estatísticas de avaliação em todos os arquivos.

### Parâmetros

Nenhum.

### Resposta

```json
{
  "total_rated": 1234,
  "distribution": {
    "1": 50,
    "2": 100,
    "3": 300,
    "4": 500,
    "5": 284
  }
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `total_rated` | int | Número total de arquivos com classificação |
| `distribution` | object | Contagem de arquivo por valor de avaliação (1–5) |
