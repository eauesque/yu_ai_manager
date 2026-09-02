# API de Integração GitHub

APIs para gerenciamento de conta GitHub, issues, pull requests, notificações e releases.

Fornecido pela extensão `builtin-github`. Todos os endpoints requerem autenticação (sessão PIN ou API Key).

## Gerenciamento de Conta

### GET /api/github/accounts

Lista contas GitHub registradas. Tokens são mascarados na resposta.

### Resposta

```json
{
  "data": [
    {
      "label": "my-account",
      "token": "ghp_****...xxxx",
      "repos": ["owner/repo1", "owner/repo2"],
      "enabled": true
    }
  ]
}
```

### POST /api/github/accounts

Registra uma nova conta GitHub.

### Solicitação

```json
{
  "label": "my-account",
  "token": "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "repos": ["owner/repo1", "owner/repo2"]
}
```

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|----------|-----------|
| `label` | string | Sim | Rótulo de identificador único de conta |
| `token` | string | Sim | Token de Acesso Pessoal GitHub |
| `repos` | string[] | Sim | Repositórios a monitorar (formato `owner/repo`) |

### Resposta

```json
{
  "data": { "label": "my-account", "status": "created" }
}
```

### PUT /api/github/accounts/<label>

Atualiza as configurações de uma conta existente.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `label` | string | Rótulo de conta (parâmetro de caminho) |

### Solicitação

```json
{
  "token": "ghp_new_token_value",
  "repos": ["owner/repo1", "owner/repo3"],
  "enabled": false
}
```

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|----------|-----------|
| `token` | string | Não | Novo valor de token |
| `repos` | string[] | Não | Lista de repositórios atualizada |
| `enabled` | boolean | Não | Habilitar ou desabilitar a conta |

### DELETE /api/github/accounts/<label>

Remove uma conta.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `label` | string | Rótulo de conta (parâmetro de caminho) |

---

## Issues

### GET /api/github/issues/<label>

Busca issues dos repositórios da conta.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `label` | string | Rótulo de conta (parâmetro de caminho) |
| `state` | string | Filtro de estado da issue (`open`, `closed`, `all`) |
| `labels` | string | Filtro de rótulo (separados por vírgula) |
| `since` | string | Issues atualizadas após esta data (ISO 8601) |
| `repo` | string | Filtrar para um repositório específico (`owner/repo`) |

### Exemplo curl

```bash
curl -H "Authorization: Bearer sk_xxxxx" \
  "http://localhost:5000/api/github/issues/my-account?state=open&repo=owner/repo1"
```

### POST /api/github/issues/<label>

Cria uma nova issue.

### Solicitação

```json
{
  "repo": "owner/repo1",
  "title": "Bug: crash on login screen",
  "body": "Steps to reproduce:\n1. ...\n2. ...",
  "labels": ["bug", "priority:high"]
}
```

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|----------|-----------|
| `repo` | string | Sim | Repositório alvo (`owner/repo`) |
| `title` | string | Sim | Título da issue |
| `body` | string | Não | Corpo da issue (Markdown) |
| `labels` | string[] | Não | Rótulos a aplicar |

### GET /api/github/issue/<label>/<repo>/<number>

Recupera detalhes da issue incluindo comentários.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `label` | string | Rótulo de conta |
| `repo` | string | Nome do repositório (`owner/repo`) |
| `number` | int | Número da issue |

### POST /api/github/triage/<label>

Executa triagem de issue (classificação e priorização).

### Solicitação

```json
{
  "state": "open",
  "since": "2026-03-01T00:00:00Z"
}
```

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|----------|-----------|
| `state` | string | Não | Filtro de estado para issues alvo |
| `since` | string | Não | Apenas triage issues atualizadas após esta data (ISO 8601) |

---

## Pull Requests

### GET /api/github/pulls/<label>

Lista pull requests.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `label` | string | Rótulo de conta (parâmetro de caminho) |
| `state` | string | Estado PR (`open`, `closed`, `all`) |
| `repo` | string | Filtrar para um repositório específico (`owner/repo`) |

### GET /api/github/pull/<label>/<repo>/<number>

Recupera detalhes PR incluindo arquivos alterados.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `label` | string | Rótulo de conta |
| `repo` | string | Nome do repositório (`owner/repo`) |
| `number` | int | Número do PR |

---

## Notificações

### GET /api/github/notifications/<label>

Lista notificações.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `label` | string | Rótulo de conta (parâmetro de caminho) |
| `all` | string | Defina como `true` para incluir notificações lidas (padrão: apenas não lidas) |

### PATCH /api/github/notifications/<label>/<thread_id>

Marca um thread de notificação específico como lido.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `label` | string | Rótulo de conta |
| `thread_id` | string | ID do thread de notificação |

### POST /api/github/notifications/<label>/mark-all-read

Marca todas as notificações como lidas.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `label` | string | Rótulo de conta (parâmetro de caminho) |

---

## Discussões

### GET /api/github/discussions/<label>

Busca Discussões GitHub (via API GraphQL).

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `label` | string | Rótulo de conta (parâmetro de caminho) |
| `repo` | string | Filtrar para um repositório específico (`owner/repo`) |

---

## Releases

### GET /api/github/releases/<label>

Lista releases.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `label` | string | Rótulo de conta (parâmetro de caminho) |
| `repo` | string | Filtrar para um repositório específico (`owner/repo`) |

---

## Estatísticas de Repositório

### GET /api/github/repo-stats/<label>/<repo>

Recupera estatísticas para um único repositório.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `label` | string | Rótulo de conta |
| `repo` | string | Nome do repositório (`owner/repo`) |

### GET /api/github/repo-stats-all/<label>

Recupera estatísticas para todos os repositórios registrados de uma vez.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `label` | string | Rótulo de conta (parâmetro de caminho) |

---

## Taxa de Limite

### GET /api/github/rate-limit/<label>

Verifica o status de taxa de limite da API GitHub.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `label` | string | Rótulo de conta (parâmetro de caminho) |

### Exemplo de Resposta

```json
{
  "data": {
    "rate": {
      "limit": 5000,
      "remaining": 4832,
      "reset": 1710500000
    }
  }
}
```

---

## Prompts de Triagem

### GET /api/github/triage-prompts

Obtém prompts de triagem editáveis para issue/PR/discussão, juntamente com seus valores padrão.

### Resposta

```json
{
  "data": {
    "prompts": {
      "issue": "Review the following GitHub issue...",
      "pr": "Do not accept pull requests. Close automatically.",
      "discussion": "Discussions are closed. No action required."
    },
    "defaults": {
      "issue": "Review the following GitHub issue...",
      "pr": "Do not accept pull requests. Close automatically.",
      "discussion": "Discussions are closed. No action required."
    }
  }
}
```

### PUT /api/github/triage-prompts

Atualiza prompts de triagem. Apenas campos fornecidos são atualizados.

### Solicitação

```json
{
  "issue": "Custom issue triage prompt...",
  "pr": "Custom PR prompt...",
  "discussion": "Custom discussion prompt..."
}
```

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|----------|-----------|
| `issue` | string | Não | Prompt de triagem para issues |
| `pr` | string | Não | Prompt de triagem para pull requests |
| `discussion` | string | Não | Prompt de triagem para discussões |

---

## Fila de Issue

### GET /api/github/queue

Obtém itens de fila de issue com filtro de status opcional.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `status` | string | Filtro: `pending`, `notified`, `dismissed`, ou vazio para todos |
| `limit` | int | Máx resultados (padrão 50, máx 200) |

### Resposta

```json
{
  "data": {
    "items": [
      {
        "id": 1,
        "repo": "owner/repo",
        "issue_number": 42,
        "title": "Bug report title",
        "body": "Issue body...",
        "created_at": "2026-03-15T10:00:00Z",
        "fetched_at": "2026-03-15T12:00:00Z",
        "status": "pending",
        "triage_result": "pending"
      }
    ],
    "stats": { "pending": 3, "notified": 1, "dismissed": 5, "total": 9 }
  }
}
```

### GET /api/github/queue/pending

Obtém issues pendentes (não lidas) para notificação MCP.

### Resposta

```json
{
  "data": {
    "items": [...],
    "count": 3
  }
}
```

### POST /api/github/queue/<queue_id>/triage

Define resultado de triagem para um item de fila.

### Solicitação

```json
{ "result": "valid" }
```

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|----------|-----------|
| `result` | string | Sim | `valid` ou `invalid` |

### POST /api/github/queue/<queue_id>/dismiss

Descartas um item de fila. Opcionalmente fecha a issue no GitHub automaticamente.

### Solicitação

```json
{
  "auto_close": true,
  "account_label": "my-account"
}
```

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|----------|-----------|
| `auto_close` | boolean | Não | Fecha a issue no GitHub com comentário de template |
| `account_label` | string | Não | Obrigatório se `auto_close` é true |

### PUT /api/github/queue/<queue_id>/status

Atualiza status do item de fila.

### Solicitação

```json
{ "status": "notified" }
```

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|----------|-----------|
| `status` | string | Sim | `pending`, `notified`, ou `dismissed` |

### GET /api/github/queue/config

Obtém configuração de fila de issue.

### Resposta

```json
{
  "data": {
    "poll_interval_minutes": 60,
    "auto_close_invalid": false,
    "notify_on_connect": true
  }
}
```

### PUT /api/github/queue/config

Atualiza configuração de fila de issue.

### Solicitação

```json
{
  "poll_interval_minutes": 30,
  "auto_close_invalid": true,
  "notify_on_connect": true
}
```

### POST /api/github/queue/poll

Dispara sondagem imediata de todas as contas para novas issues.

---

## WebUI

### GET /ext/github

Página WebUI de Integração GitHub. Acesse diretamente no navegador.

Requer uma sessão PIN autenticada.
