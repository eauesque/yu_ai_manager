# API de Extensões

APIs para gerenciar extensões, instalação, segurança e autoria.

---

## GET /api/extensions

Lista todas as extensões instaladas.

### Parâmetros

Nenhum

### Resposta

```json
{
  "extensions": [
    {
      "name": "builtin-sd-webui-bridge",
      "version": "1.0.0",
      "description": "SD WebUI Bridge",
      "enabled": true,
      "trust_level": "trusted",
      "category": "integration",
      "directory": "extensions/builtin_sd_webui_bridge"
    }
  ],
  "total": 5,
  "category_order": ["core", "integration", "tools", "ui", "other"]
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `extensions` | array | Array de informações de extensão |
| `total` | int | Número total de extensões |
| `category_order` | string[] | Ordem de exibição de categorias |

## GET /api/extensions/\<name\>

Obter informações detalhadas sobre uma extensão específica.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `name` | string | Nome da extensão (parâmetro de caminho) |

### Resposta

```json
{
  "name": "builtin-sd-webui-bridge",
  "version": "1.0.0",
  "description": "SD WebUI Bridge",
  "enabled": true,
  "trust_level": "trusted",
  "category": "integration",
  "directory": "extensions/builtin_sd_webui_bridge"
}
```

### Erros

- `404` — Extensão não encontrada

## POST /api/extensions/\<name\>/toggle

Alternar o estado ativado/desativado de uma extensão.

### Limite de Taxa

WRITE

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `name` | string | Nome da extensão (parâmetro de caminho) |

### Solicitação

```json
{
  "enabled": true
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `enabled` | boolean | Não | `true` para ativar, `false` para desativar. Omita para alternar (inverter estado atual) |

### Resposta

```json
{
  "name": "builtin-sd-webui-bridge",
  "enabled": true,
  "message": "Extension 'builtin-sd-webui-bridge' enabled"
}
```

### Erros

- `404` — Extensão não encontrada

## GET /api/extensions/\<name\>/config

Obter o esquema de configuração e valores atuais de uma extensão.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `name` | string | Nome da extensão (parâmetro de caminho) |

### Resposta

```json
{
  "name": "builtin-sd-webui-bridge",
  "config_schema": {
    "fields": [
      {
        "key": "api_url",
        "label": "API URL",
        "type": "text",
        "default": "http://127.0.0.1:7860",
        "value": "http://127.0.0.1:7860"
      }
    ]
  }
}
```

### Erros

- `404` — Extensão não encontrada

## POST /api/extensions/\<name\>/config

Salvar valores de configuração de extensão. Inclui validação.

### Limite de Taxa

WRITE

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `name` | string | Nome da extensão (parâmetro de caminho) |

### Solicitação

```json
{
  "values": {
    "api_url": "http://127.0.0.1:7860",
    "timeout": 30
  }
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `values` | object | Sim | Mapa de chaves de campo para valores |

### Resposta

```json
{
  "ok": true,
  "saved": {
    "api_url": "http://127.0.0.1:7860",
    "timeout": 30
  }
}
```

### Erros

- `404` — Extensão não encontrada
- `400` — Erro de validação

---

## Instalação / Atualização / Desinstalação de Extensão

Os seguintes endpoints são restritos ao **acesso somente de localhost**. Solicitações remotas retornam `403`.

## POST /api/extensions/install

Instalar uma extensão de um repositório Git.

### Limite de Taxa

WRITE

### Restrição de Acesso

Somente localhost

### Solicitação

```json
{
  "url": "https://github.com/user/my-extension.git"
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `url` | string | Sim | URL do repositório Git. `git` e `repo` são aceitos como aliases |

### Resposta

```json
{
  "ok": true,
  "name": "my-extension",
  "message": "Extension installed successfully"
}
```

### Erros

- `400` — URL não fornecida ou formato de URL inválido
- `403` — Acesso de não-localhost

## POST /api/extensions/\<name\>/update

Atualizar uma extensão específica para a versão mais recente (git pull).

### Limite de Taxa

WRITE

### Restrição de Acesso

Somente localhost

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `name` | string | Nome da extensão (parâmetro de caminho) |

### Resposta

```json
{
  "ok": true,
  "name": "my-extension",
  "message": "Extension updated successfully"
}
```

### Erros

- `403` — Acesso de não-localhost
- `404` — Extensão não encontrada

## POST /api/extensions/update-all

Atualização em lote de todas as extensões instaladas do Git.

### Limite de Taxa

WRITE

### Restrição de Acesso

Somente localhost

### Resposta

```json
{
  "results": [
    {"name": "my-extension", "ok": true, "message": "Updated"},
    {"name": "other-ext", "ok": false, "error": "Git pull failed"}
  ]
}
```

### Erros

- `403` — Acesso de não-localhost

## DELETE /api/extensions/\<name\>/uninstall

Desinstalar uma extensão (excluir diretório).

### Limite de Taxa

DESTRUCTIVE

### Restrição de Acesso

Somente localhost

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `name` | string | Nome da extensão (parâmetro de caminho) |

### Resposta

```json
{
  "ok": true,
  "name": "my-extension",
  "message": "Extension uninstalled"
}
```

### Erros

- `403` — Acesso de não-localhost
- `404` — Extensão não encontrada

---

## Segurança e Permissões

## GET /api/extensions/\<name\>/permissions

Obter informações de permissão e estado de aprovação de uma extensão.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `name` | string | Nome da extensão (parâmetro de caminho) |

### Resposta

```json
{
  "name": "my-extension",
  "trust_level": "L2",
  "approved": true,
  "permissions": {
    "required": [
      {"name": "network", "reason": "API calls to external service"}
    ],
    "optional": [
      {"name": "filesystem_read", "reason": "Read user images"}
    ]
  },
  "granted": {
    "granted": ["network", "filesystem_read"],
    "denied": [],
    "granted_at": "2025-01-15T10:30:00",
    "auto_approved": false
  }
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `trust_level` | string | Nível de confiança (`trusted`, `L1`, `L2`) |
| `approved` | boolean | Se o usuário aprovou essa extensão |
| `permissions.required` | array | Lista de permissões obrigatórias |
| `permissions.optional` | array | Lista de permissões opcionais |
| `granted` | object/null | Detalhes das permissões concedidas. `null` se ainda não aprovado |

### Erros

- `404` — Extensão não encontrada

## POST /api/extensions/\<name\>/permissions

Aprovar ou revogar permissões de extensão.

### Limite de Taxa

WRITE

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `name` | string | Nome da extensão (parâmetro de caminho) |

### Solicitação (Aprovar)

```json
{
  "action": "approve",
  "granted": ["network", "filesystem_read"],
  "denied": ["filesystem_write"]
}
```

### Solicitação (Revogar)

```json
{
  "action": "revoke"
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `action` | string | Não | `"approve"` (padrão) ou `"revoke"` |
| `granted` | string[] | Não | Lista de nomes de permissão para conceder (para aprovação) |
| `denied` | string[] | Não | Lista de nomes de permissão para negar (para aprovação) |

### Resposta (Aprovar)

```json
{
  "name": "my-extension",
  "action": "approved",
  "granted": ["network", "filesystem_read"],
  "denied": ["filesystem_write"]
}
```

### Resposta (Revogar)

```json
{
  "name": "my-extension",
  "action": "revoked"
}
```

### Erros

- `400` — `granted` não é uma lista
- `404` — Extensão não encontrada

## GET /api/extensions/\<name\>/scan-results

Obter resultados de análise estática do código de extensão. Retorna resultados tanto de ManifestAuthority quanto de CodeVerifier.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `name` | string | Nome da extensão (parâmetro de caminho) |

### Resposta

```json
{
  "name": "my-extension",
  "trust_level": "L2",
  "manifest_review": {
    "approved": true,
    "issues": []
  },
  "code_scan": {
    "approved": true,
    "findings": [
      {
        "file": "my_ext.py",
        "line": 15,
        "severity": "warning",
        "message": "Uses subprocess module"
      }
    ]
  }
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `manifest_review.approved` | boolean | Se o manifest passou na revisão |
| `manifest_review.issues` | array | Lista de problemas (`severity`, `message`) |
| `code_scan` | object/null | Resultados de varredura de código. `null` se sem diretório |
| `code_scan.findings` | array | Lista de descobertas |

### Erros

- `404` — Extensão não encontrada

## POST /api/extensions/\<name\>/rescan

Re-analisar o código de extensão. Retorna o mesmo formato de resultado que `scan-results`.

### Limite de Taxa

WRITE

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `name` | string | Nome da extensão (parâmetro de caminho) |

### Resposta

Mesmo formato que `GET /api/extensions/<name>/scan-results`.

## GET /api/extensions/\<name\>/tokens

Obter status de emissão de token de capacidade para uma extensão.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `name` | string | Nome da extensão (parâmetro de caminho) |

### Resposta

```json
{
  "name": "my-extension",
  "token_count": 2,
  "tokens": [
    {
      "capability": "network",
      "issued_at": "2025-01-15T10:30:00",
      "expires_at": "2025-01-16T10:30:00"
    }
  ]
}
```

### Erros

- `404` — Extensão não encontrada

## GET /api/extensions/\<name\>/integrity

Obter status de integridade de arquivo para uma extensão. Também inclui informações de rastreador de revogação e proteção de importação.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `name` | string | Nome da extensão (parâmetro de caminho) |

### Resposta

```json
{
  "name": "my-extension",
  "integrity": {
    "verified": true,
    "last_check": "2025-01-15T10:30:00",
    "files_changed": 0
  },
  "revocation": {
    "denial_count": 0,
    "last_access": null
  },
  "import_guard": {
    "import_denial_count": 0
  }
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `integrity` | object | Resultados da verificação de integridade de arquivo |
| `revocation` | object | Informações de rastreador de revogação de token |
| `import_guard` | object | Contagem de negação de proteção de importação |

### Erros

- `404` — Extensão não encontrada

---

## Hooks & Marketplace

## GET /api/extensions/hooks

Listar hooks de extensão registrados e definições de hook.

### Parâmetros

Nenhum

### Resposta

```json
{
  "hooks": {
    "after_scan": [
      {"extension": "builtin-tagger", "priority": 100}
    ]
  },
  "definitions": {
    "after_scan": {"mode": "sequential"},
    "before_import": {"mode": "sequential"}
  }
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `hooks` | object | Mapa de nomes de hook para listas de extensões registradas |
| `definitions` | object | Definições de hook disponíveis. `mode` é o modo de execução |

## GET /api/extensions/marketplace

Buscar extensões de marketplace.

### Parâmetros

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `q` | string | Não | Consulta de busca (parâmetro de query). String vazia retorna tudo |

### Resposta

```json
{
  "extensions": [
    {
      "name": "awesome-extension",
      "description": "An awesome extension",
      "author": "developer",
      "version": "1.0.0",
      "installed": false
    }
  ],
  "total": 10
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `extensions` | array | Informações de extensão do marketplace |
| `extensions[].installed` | boolean | Se a extensão está instalada localmente |
| `total` | int | Número total de resultados de busca |

## POST /api/extensions/marketplace/refresh

Forçar atualização do cache do marketplace.

### Limite de Taxa

WRITE

### Resposta

```json
{
  "refreshed": true,
  "total": 25
}
```

---

## Isolamento

## GET /api/extensions/isolation

Obter status de isolamento de processo.

### Parâmetros

Nenhum

### Resposta

```json
{
  "available": true,
  "processes": {
    "my-extension": {
      "pid": 12345,
      "status": "running"
    }
  }
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `available` | boolean | Se isolamento de processo está disponível |
| `processes` | object | Mapa de nomes de extensão para status de processo |

## GET /api/extensions/os-isolation

Obter status de isolamento em nível do SO (Phase D). Também inclui informações de isolamento de processo.

### Parâmetros

Nenhum

### Resposta

```json
{
  "os_isolation": {
    "platform": "linux",
    "available_backends": ["apparmor"]
  },
  "config": {
    "enabled": true,
    "apparmor": true,
    "macos_sandbox_exec": false,
    "macos_user_isolation": false,
    "windows_restricted_token": false,
    "windows_job_object": false
  },
  "processes": {}
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `os_isolation` | object | Informações de isolamento em nível do SO |
| `config.enabled` | boolean | Se isolamento do SO está ativado |
| `config.apparmor` | boolean | Status de uso de AppArmor (Linux) |
| `config.macos_sandbox_exec` | boolean | Status de uso de sandbox-exec do macOS |
| `config.macos_user_isolation` | boolean | Status de isolamento de usuário do macOS |
| `config.windows_restricted_token` | boolean | Status de uso de token restrito do Windows |
| `config.windows_job_object` | boolean | Status de uso de Job Object do Windows |
| `processes` | object | Status de isolamento de processo |

---

## Autoria de Extensão

APIs para criação e edição de extensões personalizadas. Baseado no modelo de concessão, apenas o diretório `extensions/custom-{name}/` é gravável.

Todos os endpoints são restritos ao **acesso somente de localhost**.

### Restrições de Segurança

- Nome da extensão: apenas alfanumérico minúsculo e hifens (`[a-z0-9-]`), máximo 50 caracteres, prefixo `builtin-` proibido
- Tipos de arquivo: apenas whitelist (`entrypoint`, `template`, `static_css`, `static_js`, `config`, `readme`)
- Arquivos binários: completamente proibido
- Limites de tamanho de arquivo: 10KB a 50KB dependendo do tipo

## POST /api/extensions/author/create

Criar uma nova extensão personalizada com arquivos de scaffold.

### Limite de Taxa

WRITE

### Restrição de Acesso

Somente localhost

### Solicitação

```json
{
  "name": "my-tool",
  "description": "A useful tool extension"
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `name` | string | Sim | Nome da extensão (`[a-z0-9-]`, máximo 50 caracteres) |
| `description` | string | Não | Descrição da extensão |

### Resposta

```json
{
  "ok": true,
  "name": "custom-my-tool",
  "path": "extensions/custom-my-tool",
  "files": [
    "extension.json",
    "my_tool_ext.py"
  ]
}
```

### Erros

- `400` — Nome inválido ou extensão já existe
- `403` — Acesso de não-localhost

## POST /api/extensions/author/\<name\>/write

Escrever um arquivo em uma extensão personalizada.

### Limite de Taxa

WRITE

### Restrição de Acesso

Somente localhost

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `name` | string | Nome da extensão (parâmetro de caminho, sem prefixo `custom-`) |

### Solicitação

```json
{
  "file_type": "entrypoint",
  "filename": "my_tool_ext",
  "content": "\"\"\"My tool extension.\"\"\"\n\nfrom quart import Blueprint\n..."
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `file_type` | string | Sim | Tipo de arquivo. Um de: `entrypoint`, `template`, `static_css`, `static_js`, `config`, `readme` |
| `filename` | string | Sim | Nome do arquivo sem extensão. Apenas alfanumérico, hifens e underscores |
| `content` | string | Sim | Conteúdo do arquivo (apenas texto) |

### Restrições de Tipo de Arquivo

| file_type | Extensão | Tamanho Máx | Notas |
|-----------|-----------|----------|-------|
| `entrypoint` | `.py` | 50KB | Entrypoint de extensão |
| `template` | `.html` | 50KB | Colocado em `templates/{name}/` |
| `static_css` | `.css` | 50KB | Colocado em `static/` |
| `static_js` | `.js` | 50KB | Colocado em `static/` |
| `config` | `.json` | 10KB | Filename must be `extension` |
| `readme` | `.md` | 20KB | Filename must be `README` |

### Resposta

```json
{
  "ok": true,
  "file": "my_tool_ext.py",
  "size": 256
}
```

### Erros

- `400` — Erro de validação (nome inválido, tipo de arquivo, tamanho excedido, binário detectado)
- `403` — Acesso de não-localhost

## GET /api/extensions/author/\<name\>/read

Ler um arquivo de uma extensão personalizada.

### Restrição de Acesso

Somente localhost

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `name` | string | Nome da extensão (parâmetro de caminho) |

### Parâmetros de Query

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `file_type` | string | Sim | Tipo de arquivo |
| `filename` | string | Sim | Nome do arquivo sem extensão |

### Resposta

```json
{
  "ok": true,
  "file": "my_tool_ext.py",
  "content": "\"\"\"My tool extension.\"\"\"\n...",
  "size": 256
}
```

### Erros

- `400` — Erro de validação
- `403` — Acesso de não-localhost

## GET /api/extensions/author/\<name\>/files

Listar todos os arquivos em uma extensão personalizada.

### Restrição de Acesso

Somente localhost

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `name` | string | Nome da extensão (parâmetro de caminho) |

### Resposta

```json
{
  "ok": true,
  "name": "custom-my-tool",
  "files": [
    {"path": "extension.json", "size": 320},
    {"path": "my_tool_ext.py", "size": 256},
    {"path": "templates/my_tool/index.html", "size": 1024}
  ],
  "total_size": 1600
}
```

### Erros

- `400` — Nome de extensão inválido
- `403` — Acesso de não-localhost

## POST /api/extensions/author/\<name\>/validate

Validar extension.json e código de uma extensão personalizada. Executa CodeVerifier sem registrar a extensão.

### Limite de Taxa

WRITE

### Restrição de Acesso

Somente localhost

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `name` | string | Nome da extensão (parâmetro de caminho) |

### Resposta (Sucesso)

```json
{
  "ok": true,
  "name": "custom-my-tool",
  "issues": [],
  "code_findings": [],
  "manifest": {
    "name": "custom-my-tool",
    "version": "0.1.0",
    "entrypoint": "my_tool_ext.py"
  }
}
```

### Resposta (Problemas Encontrados)

```json
{
  "ok": false,
  "name": "custom-my-tool",
  "issues": [
    "Missing required field: version",
    "CodeVerifier rejected: dangerous patterns detected"
  ],
  "code_findings": [
    {
      "severity": "critical",
      "message": "Uses eval()",
      "file": "my_tool_ext.py",
      "line": 42
    }
  ],
  "manifest": {}
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `ok` | boolean | Se todas as verificações passaram |
| `issues` | string[] | Problemas de verificação de manifest e código |
| `code_findings` | array | Descobertas de CodeVerifier |
| `manifest` | object | Conteúdo parsed de extension.json |

### Erros

- `400` — Nome de extensão inválido ou extensão não existe
- `403` — Acesso de não-localhost
