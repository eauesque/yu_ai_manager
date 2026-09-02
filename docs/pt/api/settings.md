# API de Configurações

APIs para gerenciar configurações da aplicação, criptografia de segredos e integração de gerenciador de senhas externo (1Password / Bitwarden).

Valores secretos são sempre mascarados (`****`) nas respostas GET. O campo `source` indica qual backend o valor foi resolvido.

## Autenticação

Todos os endpoints requerem autenticação por PIN ou autenticação por chave de API.

---

## GET /api/settings/schema

Recupera a definição completa do esquema de configurações. Retorna nomes de chaves, tipos, padrões, categorias e outros metadados para todas as configurações.

### Parâmetros

Nenhum

### Resposta

```json
{
  "schema": [
    {
      "key": "pin",
      "type": "str",
      "default": "",
      "category": "security",
      "secret": true,
      "label": "PIN Code"
    }
  ]
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `key` | string | Chave de configuração (separada por ponto, ex: `github.token`) |
| `type` | string | Tipo de valor (`str`, `int`, `float`, `bool`) |
| `default` | any | Valor padrão |
| `category` | string | Nome da categoria |
| `secret` | bool | Se é um valor secreto |
| `label` | string | Rótulo de exibição |

---

## GET /api/settings/all

Recupera todos os valores de configuração. Valores secretos são retornados de forma mascarada.

### Parâmetros

Nenhum

### Resposta

```json
{
  "settings": [
    {
      "key": "pin",
      "value": "****",
      "source": "encrypted",
      "secret": true,
      "category": "security"
    },
    {
      "key": "theme",
      "value": "dark",
      "source": "config",
      "secret": false,
      "category": "appearance"
    }
  ]
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `key` | string | Chave de configuração |
| `value` | any | Valor atual (mascarado se secreto) |
| `source` | string | Fonte do valor: `default` / `config` / `encrypted` / `1password` / `bitwarden` |
| `secret` | bool | Se é um valor secreto |
| `category` | string | Nome da categoria |

---

## GET /api/settings/\<key\>

Recupera um valor de configuração individual. A chave usa formato de caminho separado por ponto (ex: `github.token`).

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `key` | string | Chave de configuração (parâmetro de caminho) |

### Resposta

```json
{
  "key": "github.token",
  "value": "****",
  "source": "1password",
  "secret": true,
  "category": "integrations"
}
```

### Erros

| Status | Código | Descrição |
|--------|--------|-------------|
| 404 | `not_found` | Chave de configuração desconhecida |

---

## PUT /api/settings/\<key\>

Atualiza um valor de configuração. Valores secretos são automaticamente criptografados. Opcionalmente especifique uma URI do 1Password para gerenciar o segredo externamente.

### Limite de Taxa

DESTRUCTIVE

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `key` | string | Chave de configuração (parâmetro de caminho) |

### Requisição

```json
{
  "value": "new-value",
  "op_uri": "op://vault/item/field"
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `value` | any | Sim | O valor a ser definido. Automaticamente coagido para o tipo definido no esquema |
| `op_uri` | string | Não | URI do 1Password. Quando especificado, salva um mapeamento `op_secrets` em vez do valor |

### Resposta

```json
{
  "key": "github.token",
  "updated": true
}
```

### Erros

| Status | Código | Descrição |
|--------|--------|-------------|
| 400 | `bad_request` | Corpo da requisição sem `value` |
| 404 | `not_found` | Chave de configuração desconhecida |

---

## GET /api/settings/secrets/status

Recupera o status do backend da chave de criptografia. Mostra qual método de gerenciamento de chaves está sendo usado.

### Parâmetros

Nenhum

### Resposta

```json
{
  "backend": "keychain",
  "available": true,
  "keychain_supported": true
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `backend` | string | Backend de chave atual (`keychain` / `passphrase` / `file`) |
| `available` | bool | Se a criptografia está disponível |
| `keychain_supported` | bool | Se o chaveiro do SO é suportado |

---

## POST /api/settings/secrets/export

Exporta a chave de criptografia como JSON protegido por senha. Usado para backup ou migração para outro ambiente.

### Limite de Taxa

DESTRUCTIVE

### Requisição

```json
{
  "password": "my-export-password"
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `password` | string | Sim | Senha para proteger os dados exportados |

### Resposta

```json
{
  "success": true,
  "export_data": "base64-encoded-encrypted-key-data"
}
```

### Erros

| Status | Código | Descrição |
|--------|--------|-------------|
| 400 | `bad_request` | Corpo da requisição sem `password` |
| 400 | `export_failed` | Operação de exportação falhou |

---

## POST /api/settings/secrets/import

Importa uma chave de criptografia de dados previamente exportados.

### Limite de Taxa

DESTRUCTIVE

### Requisição

```json
{
  "export_data": "base64-encoded-encrypted-key-data",
  "password": "my-export-password"
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `export_data` | string | Sim | Os dados obtidos durante a exportação |
| `password` | string | Sim | A senha definida durante a exportação |

### Resposta

```json
{
  "success": true,
  "message": "Key imported successfully"
}
```

### Erros

| Status | Código | Descrição |
|--------|--------|-------------|
| 400 | `bad_request` | `export_data` ou `password` ausentes |
| 400 | `import_failed` | Senha incorreta ou dados corrompidos |

---

## POST /api/settings/secrets/migrate-keychain

Migra a chave de criptografia do backend de arquivo para o chaveiro do SO. Suporta Keychain do macOS, Credential Manager do Windows e Secret Service do Linux.

### Limite de Taxa

DESTRUCTIVE

### Requisição

Nenhuma (nenhum corpo obrigatório)

### Resposta

```json
{
  "success": true,
  "message": "Key migrated to OS keychain"
}
```

### Erros

| Status | Código | Descrição |
|--------|--------|-------------|
| 400 | `migration_failed` | Chaveiro indisponível ou migração falhou |

---

## GET /api/settings/op-status

Recupera o status de conexão do CLI do 1Password (`op`).

### Parâmetros

Nenhum

### Resposta

```json
{
  "available": true,
  "signed_in": true,
  "version": "2.24.0"
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `available` | bool | Se o comando `op` existe no PATH |
| `signed_in` | bool | Se está conectado ao 1Password |
| `version` | string | Versão do CLI `op` |

---

## GET /api/settings/secrets/op-vaults

Lista os cofres disponíveis do 1Password.

### Parâmetros

Nenhum

### Resposta

```json
{
  "vaults": [
    {
      "id": "abc123",
      "name": "Personal"
    }
  ]
}
```

### Erros

| Status | Código | Descrição |
|--------|--------|-------------|
| 503 | `op_unavailable` | CLI do 1Password não disponível |

---

## POST /api/settings/secrets/push-to-op

Grava em lote todos os segredos do 1Password e salva mapeamentos `op_secrets` em config.json.

### Limite de Taxa

DESTRUCTIVE

### Requisição

```json
{
  "vault": "Personal",
  "item_title": "YU AI Manager",
  "remove_local": false
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `vault` | string | Sim | Nome do cofre do 1Password de destino |
| `item_title` | string | Não | Título do item do 1Password. Padrão: `YU AI Manager` |
| `remove_local` | bool | Não | Se `true`, remove valores criptografados localmente de config.json após o envio. Padrão: `false` |

### Resposta

```json
{
  "message": "2 secrets pushed to 1Password",
  "pushed_keys": ["github.token", "pin"],
  "uris": {
    "github.token": "op://Personal/YU AI Manager/github.token",
    "pin": "op://Personal/YU AI Manager/pin"
  },
  "remove_local": false
}
```

### Erros

| Status | Código | Descrição |
|--------|--------|-------------|
| 400 | `bad_request` | `vault` ausente |
| 400 | `no_secrets` | Nenhum segredo para enviar |
| 500 | `op_push_failed` | Falha ao gravar no 1Password |
| 503 | `op_unavailable` | CLI do 1Password não disponível |

---

## DELETE /api/settings/op-mapping/\<key\>

Remove um mapeamento de URI do 1Password, revertendo para criptografia local.

### Limite de Taxa

WRITE

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `key` | string | Chave de configuração (parâmetro de caminho) |

### Resposta

```json
{
  "key": "github.token",
  "unlinked": true
}
```

### Erros

| Status | Código | Descrição |
|--------|--------|-------------|
| 404 | `not_found` | Chave não encontrada no mapeamento `op_secrets` |

---

## GET /api/settings/bw-status

Recupera o status de conexão do CLI do Bitwarden (`bw`).

### Parâmetros

Nenhum

### Resposta

```json
{
  "available": true,
  "status": "unlocked"
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `available` | bool | Se o comando `bw` existe no PATH |
| `status` | string | Status da sessão Bitwarden |

---

## GET /api/settings/secrets/bw-folders

Lista as pastas disponíveis do Bitwarden.

### Parâmetros

Nenhum

### Resposta

```json
{
  "folders": [
    {
      "id": "folder-uuid",
      "name": "Development"
    }
  ]
}
```

### Erros

| Status | Código | Descrição |
|--------|--------|-------------|
| 503 | `bw_unavailable` | CLI do Bitwarden não disponível |

---

## POST /api/settings/secrets/push-to-bw

Grava em lote todos os segredos do Bitwarden e salva mapeamentos `bw_secrets` em config.json.

### Limite de Taxa

WRITE

### Requisição

```json
{
  "folder_id": "folder-uuid",
  "item_name": "YU AI Manager"
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `folder_id` | string/null | Não | ID da pasta Bitwarden de destino. Omita para nenhuma pasta |
| `item_name` | string | Não | Nome do item do Bitwarden. Padrão: `YU AI Manager` |

### Resposta

```json
{
  "message": "2 secrets pushed to Bitwarden",
  "pushed_keys": ["github.token", "pin"],
  "mappings": {
    "github.token": {"item_id": "item-uuid", "field": "github.token"},
    "pin": {"item_id": "item-uuid", "field": "pin"}
  }
}
```

### Erros

| Status | Código | Descrição |
|--------|--------|-------------|
| 400 | `no_secrets` | Nenhum segredo para enviar |
| 500 | `bw_push_failed` | Falha ao gravar no Bitwarden |
| 503 | `bw_unavailable` | CLI do Bitwarden não disponível |

---

## DELETE /api/settings/bw-mapping/\<key\>

Remove um mapeamento do Bitwarden, revertendo para criptografia local.

### Limite de Taxa

WRITE

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `key` | string | Chave de configuração (parâmetro de caminho) |

### Resposta

```json
{
  "key": "github.token",
  "unlinked": true
}
```

### Erros

| Status | Código | Descrição |
|--------|--------|-------------|
| 404 | `not_found` | Chave não encontrada no mapeamento `bw_secrets` |
