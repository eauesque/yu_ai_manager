# API de Perfis

APIs para gerenciar perfis de configuração. Perfis são snapshots nomeados de configurações de aplicação, armazenados como `profiles/<name>.json`.

Todos os endpoints requerem autenticação PIN. Retorna 403 se autenticação PIN está desabilitada, ou 401 se a sessão não está autenticada.

## Regras de Nome de Perfil

- 1 a 64 caracteres
- Caracteres permitidos: `a-zA-Z0-9_-`

---

## GET /api/profiles

Lista metadados para todos os perfis. Ordenado por favoritos primeiro, depois alfabeticamente por rótulo.

### Parâmetros

Nenhum

### Resposta

```json
{
  "profiles": [
    {
      "name": "default",
      "label": "Default",
      "description": "Standard configuration",
      "favorite": true,
      "last_used_at": "2026-03-20T12:00:00Z",
      "created_at": "2026-01-01T00:00:00Z",
      "db": null,
      "is_active": true
    }
  ]
}
```

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `name` | string | Nome do perfil (usado como nome de arquivo) |
| `label` | string | Rótulo de exibição |
| `description` | string | Texto de descrição |
| `favorite` | boolean | Flag de favorito |
| `last_used_at` | string/null | Timestamp de último uso (ISO 8601) |
| `created_at` | string/null | Timestamp de criação (ISO 8601) |
| `db` | string/null | Caminho do banco de dados associado |
| `is_active` | boolean | Se este é o perfil atualmente ativo |

## GET /api/profiles/\<name\>

Obtém os dados completos de um perfil específico.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `name` | string | Nome do perfil (parâmetro de caminho) |

### Resposta

```json
{
  "profile": {
    "name": "default",
    "label": "Default",
    "description": "Standard configuration",
    "favorite": false,
    "created_at": "2026-01-01T00:00:00Z",
    "last_used_at": "2026-03-20T12:00:00Z",
    "is_active": true
  }
}
```

### Erros

| Código | Status | Descrição |
|--------|--------|-----------|
| `invalid_profile_name` | 400 | Nome de perfil inválido |
| `profile_not_found` | 404 | Perfil não existe |

## POST /api/profiles

Cria um novo perfil.

### Taxa de Limite

WRITE

### Solicitação

```json
{
  "name": "my_profile",
  "label": "My Profile",
  "description": "Custom settings",
  "base_config": {}
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `name` | string | Sim | Nome do perfil (`a-zA-Z0-9_-`, 1-64 chars) |
| `label` | string | Não | Rótulo de exibição. Padrão para `name` se omitido |
| `description` | string | Não | Texto de descrição |
| `base_config` | object | Não | Valores de configuração iniciais. Chaves que não são chaves de metadados (`name`, `label`, `description`, `favorite`, `last_used_at`, `created_at`, `db`) são copiadas no perfil |

### Resposta (201)

```json
{
  "profile": {
    "name": "my_profile",
    "label": "My Profile",
    "description": "Custom settings",
    "favorite": false,
    "created_at": "2026-03-22T00:00:00Z",
    "last_used_at": null
  }
}
```

### Erros

| Código | Status | Descrição |
|--------|--------|-----------|
| `invalid_profile_name` | 400 | Nome de perfil inválido |
| `invalid_label` | 400 | Rótulo está vazio |
| `profile_exists` | 409 | Um perfil com o mesmo nome já existe |

## PUT /api/profiles/\<name\>

Atualiza metadados do perfil. Apenas `label`, `description` e `favorite` podem ser alterados.

### Taxa de Limite

WRITE

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `name` | string | Nome do perfil (parâmetro de caminho) |

### Solicitação

```json
{
  "label": "Updated Label",
  "description": "Updated description",
  "favorite": true
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `label` | string | Não | Rótulo de exibição |
| `description` | string | Não | Texto de descrição |
| `favorite` | boolean | Não | Flag de favorito |

Pelo menos um campo deve ser fornecido.

### Resposta

```json
{
  "profile": {
    "name": "my_profile",
    "label": "Updated Label",
    "description": "Updated description",
    "favorite": true,
    "created_at": "2026-03-22T00:00:00Z",
    "last_used_at": null
  }
}
```

### Erros

| Código | Status | Descrição |
|--------|--------|-----------|
| `empty_update` | 400 | Nenhum campo especificado para atualização |
| `update_failed` | 400 | Perfil não encontrado, etc. |

## DELETE /api/profiles/\<name\>

Deleta um perfil. O perfil ativamente ativo não pode ser deletado.

### Taxa de Limite

WRITE

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `name` | string | Nome do perfil (parâmetro de caminho) |

### Resposta

```json
{
  "deleted": "my_profile"
}
```

### Erros

| Código | Status | Descrição |
|--------|--------|-----------|
| `delete_active` | 400 | Não pode deletar o perfil ativo |
| `delete_failed` | 400 | Perfil não encontrado, etc. |

## POST /api/profiles/\<name\>/duplicate

Duplica um perfil com um novo nome.

### Taxa de Limite

WRITE

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `name` | string | Nome do perfil de origem (parâmetro de caminho) |

### Solicitação

```json
{
  "new_name": "copied_profile",
  "new_label": "Copied Profile"
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `new_name` | string | Sim | Novo nome de perfil |
| `new_label` | string | Não | Novo rótulo de exibição. Padrão para `new_name` se omitido |

### Resposta (201)

```json
{
  "profile": {
    "name": "copied_profile",
    "label": "Copied Profile",
    "description": "Custom settings",
    "favorite": false,
    "created_at": "2026-03-22T00:00:00Z",
    "last_used_at": null
  }
}
```

### Erros

| Código | Status | Descrição |
|--------|--------|-----------|
| `duplicate_failed` | 400 | Origem não encontrada, novo nome inválido, ou nome já existe |

## POST /api/profiles/\<name\>/rename

Renomeia um perfil. Se o perfil ativo é renomeado, `active_profile` em `config.json` é automaticamente atualizado.

### Taxa de Limite

WRITE

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `name` | string | Nome de perfil atual (parâmetro de caminho) |

### Solicitação

```json
{
  "new_name": "renamed_profile"
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `new_name` | string | Sim | Novo nome de perfil |

### Resposta

```json
{
  "profile": {
    "name": "renamed_profile",
    "label": "My Profile",
    "description": "Custom settings",
    "favorite": false,
    "created_at": "2026-03-22T00:00:00Z",
    "last_used_at": null
  }
}
```

### Erros

| Código | Status | Descrição |
|--------|--------|-----------|
| `invalid_profile_name` | 400 | Novo nome de perfil inválido |
| `rename_failed` | 400 | Perfil de origem não encontrado ou novo nome já existe |

## POST /api/profiles/\<name\>/favorite

Alterna status de favorito de um perfil. Inverte o valor `favorite` atual.

### Taxa de Limite

WRITE

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `name` | string | Nome do perfil (parâmetro de caminho) |

### Solicitação

Nenhum corpo obrigatório.

### Resposta

```json
{
  "profile": {
    "name": "my_profile",
    "label": "My Profile",
    "favorite": true
  }
}
```

### Erros

| Código | Status | Descrição |
|--------|--------|-----------|
| `profile_not_found` | 404 | Perfil não existe |
| `favorite_failed` | 400 | Falha na atualização |

---

## Exportação / Importação de QR

Exporte e importe perfis como strings JSON para códigos QR. Campos sensíveis (contendo `pin`, `token`, `secret`, ou `key`) são automaticamente removidos durante exportação.

## GET /api/profiles/\<name\>/export

Exporta um perfil como string JSON pronta para QR. Campos sensíveis são excluídos.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `name` | string | Nome do perfil (parâmetro de caminho) |

### Resposta

```json
{
  "qr_data": "{\"schema\":\"yu://profile/1\",\"profile\":{\"name\":\"my_profile\",\"label\":\"My Profile\",\"description\":\"...\"}}"
}
```

`qr_data` é uma string JSON destinada para incorporar em um código QR. O campo `schema` identifica a versão de formato.

### Erros

| Código | Status | Descrição |
|--------|--------|-----------|
| `profile_not_found` | 404 | Perfil não existe |

## POST /api/profiles/import-preview

Visualiza uma importação de dados QR. Usado para verificar diferenças com perfis existentes. Nenhuma importação real é realizada.

### Taxa de Limite

WRITE

### Solicitação

```json
{
  "qr_data": "{\"schema\":\"yu://profile/1\",\"profile\":{\"name\":\"my_profile\",\"label\":\"My Profile\"}}"
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `qr_data` | string/object | Sim | String JSON ou objeto analisado do código QR |

### Resposta (novo perfil)

```json
{
  "mode": "new",
  "name": "my_profile",
  "label": "My Profile",
  "preview": {
    "name": "my_profile",
    "label": "My Profile",
    "description": "..."
  }
}
```

### Resposta (perfil existente)

```json
{
  "mode": "existing",
  "name": "my_profile",
  "label": "My Profile",
  "diff": {
    "description": {
      "old": "Old description",
      "new": "New description"
    }
  }
}
```

### Erros

| Código | Status | Descrição |
|--------|--------|-----------|
| `invalid_qr` | 400 | Dados QR inválidos ou chave `profile` ausente |
| `invalid_profile_name` | 400 | Nome de perfil inválido |

## POST /api/profiles/import

Importa um perfil de dados QR. Suporta três modos: criar novo, mesclagem de diff e sobrescrita completa.

### Taxa de Limite

WRITE

### Solicitação

```json
{
  "qr_data": "{\"schema\":\"yu://profile/1\",\"profile\":{\"name\":\"my_profile\",\"label\":\"My Profile\"}}",
  "mode": "full"
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `qr_data` | string/object | Sim | String JSON ou objeto analisado do código QR |
| `mode` | string | Não | Modo de importação: `full` (sobrescrita completa, padrão), `diff` (mescla apenas chaves alteradas), `new` (criar novo apenas) |

### Resposta

```json
{
  "imported": "my_profile",
  "mode": "full"
}
```

Retorna status 201 ao criar um novo perfil.

### Erros

| Código | Status | Descrição |
|--------|--------|-----------|
| `invalid_qr` | 400 | Dados QR inválidos |
| `invalid_profile_name` | 400 | Nome de perfil inválido |
| `profile_exists` | 409 | Perfil já existe quando `mode=new` |
| `import_failed` | 400 | Falha na importação |
