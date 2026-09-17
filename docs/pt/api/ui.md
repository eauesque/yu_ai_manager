# API de Gerenciamento de UI

APIs para listar, alternar, instalar e desinstalar temas de UI.

## GET /api/ui/list

Listar todas as UIs instaladas. Retorna informações de manifesto, status ativo e se templates/arquivos estáticos existem para cada UI.

### Parâmetros

Nenhum

### Resposta

```json
{
  "data": {
    "uis": [
      {
        "name": "default",
        "active": true,
        "manifest": {
          "name": "Default UI",
          "version": "1.0.0",
          "description": "Built-in reference UI"
        },
        "has_templates": true,
        "has_static": true
      },
      {
        "name": "custom-dark",
        "active": false,
        "manifest": {
          "name": "Custom Dark",
          "version": "0.2.0",
          "description": "Dark theme variant"
        },
        "has_templates": true,
        "has_static": true
      }
    ]
  }
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `name` | string | Nome do diretório da UI |
| `active` | boolean | Se esta é a UI atualmente ativa |
| `manifest` | object | Conteúdo de `manifest.json` |
| `has_templates` | boolean | Se um diretório `templates/` existe |
| `has_static` | boolean | Se um diretório `static/` existe |

## POST /api/ui/switch

Alternar a UI ativa. A mudança é salva em `config.json` e requer reinicialização do servidor para entrar em efeito.

### Limite de Taxa

WRITE

### Requisição

```json
{
  "name": "custom-dark"
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `name` | string | Sim | Nome da UI alvo. Apenas caracteres alfanuméricos, hífens e underscores são permitidos |

### Resposta

```json
{
  "name": "custom-dark",
  "restart_required": true
}
```

### Erros

| Status | Condição |
|--------|-----------|
| 400 | Nome de UI está vazio ou contém caracteres inválidos |
| 404 | UI especificada não existe |
| 400 | `manifest.json` está faltando ou inválido |
| 500 | Falha ao salvar `config.json` |

## POST /api/ui/install

Instalar uma UI de uma URL. **Apenas permitido do localhost.**

### Limite de Taxa

WRITE

### Autenticação

Requer autenticação PIN ou API Key, além disso a requisição deve originar-se do localhost. Requisições remotas são rejeitadas com 403.

### Requisição

```json
{
  "url": "https://github.com/user/my-ui/archive/refs/heads/main.zip"
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `url` | string | Sim | URL do pacote de UI (arquivo zip, etc.) |

### Resposta

```json
{
  "name": "my-ui",
  "installed": true
}
```

### Erros

| Status | Condição |
|--------|-----------|
| 400 | URL está vazio |
| 403 | Requisição não é do localhost |

## DELETE /api/ui/<name>/uninstall

Desinstalar uma UI. **Apenas permitido do localhost.** A UI padrão (`default`) não pode ser removida.

Se a UI desinstalada estiver atualmente ativa, a configuração de UI em `config.json` é resetada e a UI padrão é restaurada.

### Limite de Taxa

WRITE

### Autenticação

Requer autenticação PIN ou API Key, além disso a requisição deve originar-se do localhost. Requisições remotas são rejeitadas com 403.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `name` | string | Nome da UI (parâmetro de caminho). Apenas caracteres alfanuméricos, hífens e underscores |

### Resposta

```json
{
  "name": "custom-dark",
  "uninstalled": true
}
```

### Erros

| Status | Condição |
|--------|-----------|
| 400 | Nome de UI inválido, ou tentativa de desinstalar `default` |
| 403 | Requisição não é do localhost |
| 404 | UI especificada não existe |
