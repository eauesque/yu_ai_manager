# API de Gateway de Segurança de Agente

APIs para gerenciar controles de segurança de agentes AI. Fornece funcionalidade Kill Switch, Circuit Breaker, Orçamento, Diário de Ações, Portão de Aprovação, Escopo de Cerca, Aprovação Automática, Classificação de Ferramenta, Desfazer, Detecção de Anomalia e Escritório de Auditoria.

Todos os endpoints POST/DELETE requerem o cabeçalho `X-Requested-With` (exceto ao usar Chave de API Bearer).

---

## Kill Switch

### POST /api/agent/kill

Ativa o Kill Switch para interromper imediatamente todas as operações do agente.

#### Taxa de Limite

WRITE

#### Solicitação

```json
{
  "reason": "Manual kill via API"
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `reason` | string | Não | Motivo da parada. Padrão: `"Manual kill via API"` |

#### Resposta

```json
{
  "ok": true,
  "status": {
    "killed": true,
    "reason": "Manual kill via API",
    "killed_at": "2026-03-22T12:00:00"
  }
}
```

### POST /api/agent/resume

Desativa o Kill Switch para retomar operações do agente.

#### Taxa de Limite

WRITE

#### Solicitação

Nenhuma (corpo vazio)

#### Resposta

```json
{
  "ok": true,
  "status": {
    "killed": false,
    "reason": "",
    "killed_at": ""
  }
}
```

### GET /api/agent/status

Obtém status unificado de Kill Switch, Circuit Breaker e Orçamento.

#### Parâmetros

Nenhum

#### Resposta

```json
{
  "kill_switch": {
    "killed": false,
    "reason": "",
    "killed_at": ""
  },
  "circuit_breaker": {
    "enabled": true,
    "state": "closed",
    "failure_count": 0,
    "threshold": 5
  },
  "budget": {
    "session_id": "abc123",
    "used": 10,
    "limit": 100,
    "remaining": 90
  },
  "killed": false,
  "reason": "",
  "killed_at": ""
}
```

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `kill_switch` | object | Status detalhado do Kill Switch |
| `circuit_breaker` | object | Status detalhado do Circuit Breaker. Retorna `{"enabled": false, "state": "unknown"}` em caso de erro |
| `budget` | object | Status detalhado do Orçamento. Retorna objeto vazio em caso de erro |
| `killed` | boolean | Flag ativo de Kill Switch (nível superior para compatibilidade com versões anteriores) |
| `reason` | string | Motivo do Kill Switch (compatibilidade com versões anteriores) |
| `killed_at` | string | Hora de ativação do Kill Switch (compatibilidade com versões anteriores) |

---

## Circuit Breaker

### GET /api/agent/circuit-breaker

Obtém estado do Circuit Breaker.

#### Parâmetros

Nenhum

#### Resposta

```json
{
  "enabled": true,
  "state": "closed",
  "failure_count": 0,
  "threshold": 5
}
```

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `enabled` | boolean | Se Circuit Breaker está habilitado |
| `state` | string | Estado: `"closed"` (normal), `"open"` (acionado), `"half_open"` (sondagem) |
| `failure_count` | int | Contagem de falha consecutiva |
| `threshold` | int | Limite de contagem de falha para disparar aberto |

### POST /api/agent/circuit-breaker/reset

Reseta Circuit Breaker para estado fechado.

#### Taxa de Limite

WRITE

#### Solicitação

Nenhuma (corpo vazio)

#### Resposta

```json
{
  "ok": true,
  "status": {
    "enabled": true,
    "state": "closed",
    "failure_count": 0,
    "threshold": 5
  }
}
```

---

## Orçamento

### GET /api/agent/budget

Obtém orçamento restante para a sessão atual.

#### Parâmetros

Nenhum

#### Resposta

```json
{
  "session_id": "abc123",
  "used": 10,
  "limit": 100,
  "remaining": 90
}
```

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `session_id` | string | ID da sessão |
| `used` | int | Número de ações consumidas |
| `limit` | int | Máximo de ações permitidas |
| `remaining` | int | Ações restantes |

### POST /api/agent/budget/reset

Reseta o contador de orçamento.

#### Taxa de Limite

WRITE

#### Solicitação

Nenhuma (corpo vazio)

#### Resposta

```json
{
  "ok": true,
  "status": {
    "session_id": "abc123",
    "used": 0,
    "limit": 100,
    "remaining": 100
  }
}
```

---

## Diário de Ações

### GET /api/agent/journal

Pesquisa o Diário de Ações. Retorna histórico de ações executadas por agentes.

#### Parâmetros

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `tool_name` | string | Não | Filtrar por nome de ferramenta |
| `status` | string | Não | Filtrar por status |
| `session_id` | string | Não | Filtrar por ID de sessão |
| `limit` | int | Não | Máx resultados (padrão: 50, máx: 200) |
| `offset` | int | Não | Offset (padrão: 0) |

#### Resposta

```json
{
  "entries": [
    {
      "id": 1,
      "tool_name": "add_tags",
      "session_id": "abc123",
      "status": "completed",
      "params": {"file_id": 42, "tags": ["landscape"]},
      "result": {"ok": true},
      "created_at": "2026-03-22T12:00:00"
    }
  ],
  "total": 1
}
```

### GET /api/agent/journal/stats

Obtém estatísticas do Diário de Ações.

#### Parâmetros

Nenhum

#### Resposta

```json
{
  "total_entries": 150,
  "by_tool": {"add_tags": 50, "delete_tags": 30, "scan": 70},
  "by_status": {"completed": 140, "failed": 10}
}
```

---

## Portão de Aprovação

### GET /api/agent/approval

Obtém lista de solicitações de aprovação pendentes.

#### Parâmetros

Nenhum

#### Resposta

```json
{
  "pending": [
    {
      "request_id": "req_abc123",
      "tool_name": "purge_deleted",
      "params": {},
      "requested_at": "2026-03-22T12:00:00"
    }
  ],
  "count": 1
}
```

### POST /api/agent/approval/\<request_id\>

Responde a uma solicitação de aprovação.

#### Taxa de Limite

WRITE

#### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `request_id` | string | ID da solicitação (parâmetro de caminho) |

#### Solicitação

```json
{
  "decision": "allow"
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `decision` | string | Sim | `"allow"` (permitir), `"deny"` (rejeitar), `"always_allow"` (sempre permitir) |

#### Resposta

```json
{
  "ok": true,
  "request_id": "req_abc123",
  "decision": "allow"
}
```

#### Erros

- `400`: `decision` não é um de `allow`/`deny`/`always_allow`
- `404`: Solicitação não encontrada ou já respondida

### GET /api/agent/approval/history

Obtém histórico de aprovação.

#### Parâmetros

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `limit` | int | Não | Máx resultados (padrão: 50, máx: 200) |

#### Resposta

```json
{
  "history": [
    {
      "request_id": "req_abc123",
      "tool_name": "purge_deleted",
      "decision": "allow",
      "decided_at": "2026-03-22T12:01:00"
    }
  ]
}
```

---

## Escopo de Cerca

### GET /api/agent/scope

Obtém estado do Escopo de Cerca para todas as sessões.

#### Parâmetros

Nenhum

#### Resposta

```json
{
  "sessions": {
    "abc123": {
      "preset": "tagger",
      "denied": ["purge_deleted", "hard_delete"],
      "name": "Tagger Bot",
      "expires_at": "2026-03-22T14:00:00"
    }
  },
  "count": 1
}
```

### GET /api/agent/scope/\<session_id\>

Obtém escopo para uma sessão específica.

#### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `session_id` | string | ID da sessão (parâmetro de caminho) |

#### Resposta

```json
{
  "preset": "tagger",
  "denied": ["purge_deleted", "hard_delete"],
  "name": "Tagger Bot",
  "expires_at": "2026-03-22T14:00:00"
}
```

#### Erros

- `404`: Escopo de sessão não encontrado

### POST /api/agent/scope/\<session_id\>

Define escopo de sessão.

#### Taxa de Limite

WRITE

#### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `session_id` | string | ID da sessão (parâmetro de caminho) |

#### Solicitação

```json
{
  "preset": "tagger",
  "denied": ["purge_deleted"],
  "name": "Tagger Bot",
  "duration_hours": 2.0
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `preset` | string | Não | Nome da predefinição: `"read_only"`, `"tagger"`, `"organizer"`, `"full_access"` |
| `denied` | string[] | Não | Lista de nomes de ferramenta negados |
| `name` | string | Não | Nome de exibição para o escopo |
| `duration_hours` | number | Não | Expiração do escopo em horas |

#### Resposta

```json
{
  "ok": true,
  "scope": {
    "preset": "tagger",
    "denied": ["purge_deleted"],
    "name": "Tagger Bot",
    "expires_at": "2026-03-22T14:00:00"
  }
}
```

#### Erros

- `400`: `denied` não é uma lista

### DELETE /api/agent/scope/\<session_id\>

Deleta um escopo de sessão.

#### Taxa de Limite

WRITE

#### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `session_id` | string | ID da sessão (parâmetro de caminho) |

#### Resposta

```json
{
  "ok": true
}
```

---

## Regras de Aprovação Automática

### GET /api/agent/auto-approve

Obtém lista de regras de aprovação automática.

#### Parâmetros

Nenhum

#### Resposta

```json
{
  "rules": [
    {
      "index": 0,
      "tool": "add_tags",
      "conditions": {"max_count": 10}
    }
  ]
}
```

### POST /api/agent/auto-approve

Adiciona uma regra de aprovação automática.

#### Taxa de Limite

WRITE

#### Solicitação

```json
{
  "tool": "add_tags",
  "conditions": {"max_count": 10}
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `tool` | string | Sim | Nome da ferramenta alvo |
| `conditions` | object | Não | Condições para aprovação automática. Omitir para aprovação incondicional |

#### Resposta

```json
{
  "ok": true,
  "rule": {
    "index": 1,
    "tool": "add_tags",
    "conditions": {"max_count": 10}
  }
}
```

#### Erros

- `400`: `tool` não está especificado
- `400`: `conditions` não é um dicionário

### DELETE /api/agent/auto-approve/\<index\>

Deleta uma regra de aprovação automática.

#### Taxa de Limite

WRITE

#### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `index` | int | Índice da regra (parâmetro de caminho) |

#### Resposta

```json
{
  "ok": true
}
```

#### Erros

- `404`: Regra não encontrada

---

## Classificação de Ferramenta

### GET /api/agent/tool-levels

Obtém informações de classificação de ferramenta. Quando o parâmetro `tool` é especificado, retorna o nível para essa ferramenta específica. Caso contrário, retorna um resumo de todas as ferramentas e qualquer override.

#### Parâmetros

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `tool` | string | Não | Nome da ferramenta. Se especificado, retorna apenas o nível dessa ferramenta |

#### Resposta (ferramenta específica)

```json
{
  "tool": "purge_deleted",
  "level": "destructive"
}
```

#### Resposta (todas as ferramentas)

```json
{
  "summary": {
    "safe": ["list_files", "search_files"],
    "write": ["add_tags", "remove_tags"],
    "destructive": ["purge_deleted", "hard_delete"]
  },
  "overrides": {
    "custom_tool": "safe"
  }
}
```

---

## Desfazer

### POST /api/agent/undo/\<journal_id\>

Desfaz uma ação registrada no diário.

#### Taxa de Limite

WRITE

#### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `journal_id` | int | ID da entrada do diário (parâmetro de caminho) |

#### Resposta

```json
{
  "ok": true,
  "journal_id": 1,
  "undone_action": "add_tags"
}
```

#### Erros

- `400`: Desfazer falhou (ação não desfazível, já desfeita, etc.)

### GET /api/agent/undoable

Obtém lista de ações desfazíveis.

#### Parâmetros

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `session_id` | string | Não | Filtrar por ID de sessão |
| `limit` | int | Não | Máx resultados (padrão: 50, máx: 200) |

#### Resposta

```json
{
  "items": [
    {
      "id": 1,
      "tool_name": "add_tags",
      "session_id": "abc123",
      "params": {"file_id": 42, "tags": ["landscape"]},
      "created_at": "2026-03-22T12:00:00"
    }
  ],
  "count": 1
}
```

---

## Detecção de Anomalia

### GET /api/agent/anomaly

Obtém estado da Detecção de Anomalia.

#### Parâmetros

Nenhum

#### Resposta

```json
{
  "enabled": true,
  "window_minutes": 10,
  "thresholds": {
    "max_actions_per_window": 100,
    "max_errors_per_window": 20
  },
  "current": {
    "actions": 15,
    "errors": 0
  }
}
```

### GET /api/agent/anomaly/alerts

Obtém alertas de Detecção de Anomalia.

#### Parâmetros

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `limit` | int | Não | Máx resultados (padrão: 50, máx: 200) |

#### Resposta

```json
{
  "alerts": [
    {
      "id": 1,
      "type": "high_error_rate",
      "message": "Error rate exceeded threshold",
      "severity": "warning",
      "created_at": "2026-03-22T12:00:00"
    }
  ]
}
```

### POST /api/agent/anomaly/reset

Reseta histórico de Detecção de Anomalia e alertas.

#### Taxa de Limite

WRITE

#### Solicitação

Nenhuma (corpo vazio)

#### Resposta

```json
{
  "ok": true
}
```

---

## Escritório de Auditoria

### GET /api/agent/audit

Obtém estado do Escritório de Auditoria.

#### Parâmetros

Nenhum

#### Resposta

```json
{
  "data": {
    "total_entries": 500,
    "unacknowledged": 3,
    "last_report_at": "2026-03-22T00:00:00"
  }
}
```

### GET /api/agent/audit/log

Pesquisa o Log de Auditoria.

#### Parâmetros

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `event_type` | string | Não | Filtrar por tipo de evento |
| `severity` | string | Não | Filtrar por severidade |
| `source` | string | Não | Filtrar por origem |
| `unacknowledged` | string | Não | Defina como `"1"` ou `"true"` para retornar apenas entradas não reconhecidas |
| `limit` | int | Não | Máx resultados (padrão: 50, máx: 200) |
| `offset` | int | Não | Offset (padrão: 0) |

#### Resposta

```json
{
  "data": {
    "entries": [
      {
        "id": 1,
        "event_type": "kill_switch_activated",
        "severity": "critical",
        "source": "api",
        "message": "Kill switch activated: Manual kill via API",
        "acknowledged": false,
        "created_at": "2026-03-22T12:00:00"
      }
    ],
    "total": 1
  }
}
```

### POST /api/agent/audit/acknowledge/\<audit_id\>

Marca uma entrada de log de auditoria como reconhecida pelo usuário.

#### Taxa de Limite

WRITE

#### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `audit_id` | int | ID da entrada de log de auditoria (parâmetro de caminho) |

#### Resposta

```json
{
  "ok": true,
  "audit_id": 1
}
```

#### Erros

- `404`: Entrada não encontrada ou já reconhecida

### POST /api/agent/audit/report

Gera manualmente um relatório periódico de Escritório de Auditoria.

#### Taxa de Limite

WRITE

#### Solicitação

```json
{
  "hours": 24
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `hours` | int | Não | Período do relatório em horas. Padrão: 24, máx: 720 |

#### Resposta

```json
{
  "data": {
    "period_hours": 24,
    "total_events": 150,
    "by_severity": {"critical": 2, "warning": 10, "info": 138},
    "by_type": {"kill_switch_activated": 2, "approval_denied": 5},
    "generated_at": "2026-03-22T12:00:00"
  }
}
```
