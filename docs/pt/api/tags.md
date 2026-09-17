# API de Tags

APIs para operações em lote de tags e sugestão/autocompletar de tags.

## POST /api/tags/batch-set

Adicionar ou remover tags de múltiplos arquivos em uma única requisição.

### Limite de Taxa

WRITE (~120 req/min, burst 30)

### Corpo da Requisição

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|----------|-------------|
| `items` | array | Sim | Lista de operações (máx 500 itens) |
| `items[].file_id` | int | Sim | ID do arquivo (inteiro positivo) |
| `items[].add` | string[] | Não | Nomes de tag para adicionar |
| `items[].remove` | string[] | Não | Nomes de tag para remover |

- Cada item requer pelo menos um de `add` ou `remove`
- Tags que não existem são criadas automaticamente (namespace=null)
- Tags adicionadas via API têm sua source definida como `"user"`
- Tags órfãs (sem associações de arquivo restantes) são deletadas automaticamente

### Exemplo de Requisição

```json
{
  "items": [
    {
      "file_id": 42,
      "add": ["landscape", "sunset"],
      "remove": ["lowres"]
    }
  ]
}
```

### Resposta

```json
{
  "total": 1,
  "succeeded": 1,
  "failed": 0,
  "errors": []
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `total` | int | Número total de itens processados |
| `succeeded` | int | Número de operações bem-sucedidas |
| `failed` | int | Número de operações falhadas |
| `errors` | array | Lista de detalhes de erros |

### Erros

| Status | Descrição |
|--------|-------------|
| 400 | Corpo de requisição inválido (itens vazios, file_id inválido, add/remove ausentes, etc.) |
| 429 | Limite de taxa excedido |

---

## GET /api/tags/suggest

Retornar candidatos de tag que correspondem a uma string de busca parcial. Destinado para autocompletar.

### Parâmetros

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `q` | string | Sim | String de busca |
| `limit` | int | Não | Número máximo de resultados (padrão: 20, máx: 100) |

- Busca é insensível a maiúsculas/minúsculas (LIKE %q%)
- Resultados são classificados por `file_count` em ordem decrescente
- Um `q` vazio retorna um array vazio

### Resposta

```json
{
  "data": [
    { "id": 1, "tag": "landscape", "namespace": null, "file_count": 150 },
    { "id": 2, "tag": "1girl", "namespace": null, "file_count": 3420 }
  ]
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `data[].id` | int | ID da tag |
| `data[].tag` | string | Nome da tag |
| `data[].namespace` | string\|null | Namespace (geralmente null) |
| `data[].file_count` | int | Número de arquivos associados a esta tag |
