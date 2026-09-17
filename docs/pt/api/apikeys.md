# API de Chaves de API

APIs para criar, listar e deletar chaves de API. Todos os endpoints requerem autenticação de sessão PIN.

As chaves de API são geradas no formato `sk_` + 32 caracteres hexadecimais (128-bit). Apenas o hash é armazenado no servidor; a chave bruta é retornada apenas uma vez no momento da criação.

## Escopos

As chaves de API podem ser atribuídas escopos para restringir quais endpoints elas podem acessar. As chaves sem escopos têm acesso somente leitura por padrão.

| Escopo | Descrição |
|-------|-------------|
| `read` | Busca, detalhes de arquivo, miniaturas, stats |
| `rate` | Rating get/set/batch |
| `tag.write` | Tag add/remove |
| `collection.write` | Collection create/update/delete, batch-add, favorites |
| `annotate` | Annotation read/write/delete |
| `scan` | Scan start/cancel/resume |
| `admin` | Gerenciamento de chave de API, configurações, backup/restore |

## POST /api/apikeys

Criar uma nova chave de API.

### Limite de Taxa

WRITE (scope: `admin`)

### Autenticação

Sessão PIN ou chave de API com escopo `admin`

### Requisição

```json
{
  "label": "My Integration",
  "scopes": ["read", "rate"]
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `label` | string | Não | Rótulo de identificação para a chave. Padrão é `Key <timestamp>` se omitido |
| `scopes` | string[] | Não | Array de escopos. Omita ou passe array vazio para acesso somente leitura |

### Resposta (201)

```json
{
  "id": "ak_1a2b3c4d5e6f7890",
  "key": "sk_abcdef1234567890abcdef1234567890",
  "key_prefix": "sk_abcdef12",
  "label": "My Integration",
  "created_at": 1709500000,
  "scopes": ["read", "rate"]
}
```

> **Nota**: O campo `key` é incluído apenas na resposta de criação. Este valor não pode ser recuperado novamente, então armazene-o em um local seguro.

### Erros

| Status | Descrição |
|--------|-------------|
| 400 | Escopo inválido especificado |

## GET /api/apikeys

Listar todas as chaves de API. Os hashes não são incluídos; apenas o prefixo é retornado.

### Autenticação

Sessão PIN ou chave de API com escopo `admin`

### Parâmetros

Nenhum

### Resposta

```json
{
  "keys": [
    {
      "id": "ak_1a2b3c4d5e6f7890",
      "key_prefix": "sk_abcdef12",
      "label": "My Integration",
      "created_at": 1709500000,
      "last_used_at": 1709600000,
      "scopes": ["read", "rate"]
    }
  ]
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `id` | string | ID da chave (`ak_` prefix) |
| `key_prefix` | string | Primeiros 10 caracteres da chave (para identificação) |
| `label` | string | Rótulo definido pelo usuário |
| `created_at` | int | Hora de criação (Unix timestamp) |
| `last_used_at` | int/null | Hora do último uso. `null` se nunca usado |
| `scopes` | string[] | Escopos atribuídos. Campo é omitido se nenhum escopo for definido |

## DELETE /api/apikeys/<key_id>

Deletar (revogar) uma chave de API.

### Limite de Taxa

WRITE (scope: `admin`)

### Autenticação

Sessão PIN ou chave de API com escopo `admin`

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `key_id` | string | ID da chave de API (parâmetro de caminho) |

### Resposta

```json
{
  "deleted": "ak_1a2b3c4d5e6f7890"
}
```

### Erros

| Status | Descrição |
|--------|-------------|
| 404 | Chave com o ID especificado não encontrada |

## Usando Chaves de API

Use a chave de API criada via header `Authorization`:

```
Authorization: Bearer sk_abcdef1234567890abcdef1234567890
```

Requisições autenticadas com chaves de API não requerem o header CSRF (`X-Requested-With`).
