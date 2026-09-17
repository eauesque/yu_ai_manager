# API de Scheduler

Management API para o task scheduler. Permite verificar status, adicionar/remover jobs, pausar/retomar, disparar execução imediata e recuperar histórico de execução.

## Configuração

Habilita o scheduler e configura schedules de job built-in em `config.json`:

```json
{
  "scheduler": {
    "enabled": true,
    "jobs": {
      "db_vacuum": { "enabled": true, "trigger": "cron", "day_of_week": "sun", "hour": 3, "minute": 0 },
      "db_integrity_check": { "enabled": true, "trigger": "cron", "hour": 4, "minute": 0 },
      "thumbnail_cleanup": { "enabled": true, "trigger": "cron", "hour": 5, "minute": 0 }
    }
  }
}
```

### Built-in Jobs

| Job ID | Descrição | Schedule Padrão |
|--------|-----------|-----------------|
| `db_vacuum` | Database VACUUM (recuperar espaço) | Cada domingo às 03:00 |
| `db_integrity_check` | Verificação de integridade de banco de dados | Diariamente às 04:00 |
| `thumbnail_cleanup` | Limpeza de cache de miniatura | Diariamente às 05:00 |
| `github_issue_poll` | Polling de issues GitHub | Não definido (adicionar via WebUI) |
| `bsky_notification_poll` | Polling de notificação Bluesky | Não definido (adicionar via WebUI) |
| `prune_unused_tags` | Podar tags não utilizadas | Não definido (adicionar via WebUI) |
| `refresh_monthly_stats` | Atualizar cache de estatísticas mensais | Não definido (adicionar via WebUI) |
| `rebuild_groups_index` | Reconstruir índice de grupos | Não definido (adicionar via WebUI) |
| `db_backup` | Backup de banco de dados | Não definido (adicionar via WebUI) |

## GET /api/scheduler/status

Retorna o status do scheduler e informações sobre todos os jobs.

### Resposta

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `ok` | boolean | Flag de sucesso |
| `data.running` | boolean | Se o scheduler está em execução |
| `data.jobs` | array | Lista de jobs (incluindo próximas execuções) |

### Exemplo

```bash
curl "http://localhost:5100/api/scheduler/status"
```

```json
{
  "ok": true,
  "data": {
    "running": true,
    "jobs": [
      {
        "job_id": "db_vacuum",
        "trigger": "cron",
        "next_run": "2026-03-22T03:00:00",
        "paused": false
      },
      {
        "job_id": "db_integrity_check",
        "trigger": "cron",
        "next_run": "2026-03-16T04:00:00",
        "paused": false
      }
    ]
  }
}
```

## GET /api/scheduler/jobs

Retorna a lista de jobs com tempos `next_run`.

### Resposta

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `ok` | boolean | Flag de sucesso |
| `data.jobs` | array | Array de objetos de job |
| `data.jobs[].job_id` | string | ID do job |
| `data.jobs[].func_name` | string | Nome da função a executar |
| `data.jobs[].trigger` | string | Tipo de trigger (`cron`, `interval`, `date`) |
| `data.jobs[].next_run` | string | Próxima hora de execução agendada (ISO 8601) |
| `data.jobs[].paused` | boolean | Se o job está pausado |

### Exemplo

```bash
curl "http://localhost:5100/api/scheduler/jobs"
```

```json
{
  "ok": true,
  "data": {
    "jobs": [
      {
        "job_id": "db_vacuum",
        "func_name": "db_vacuum",
        "trigger": "cron",
        "next_run": "2026-03-22T03:00:00",
        "paused": false
      }
    ]
  }
}
```

## POST /api/scheduler/jobs

Adiciona um job customizado.

### Corpo da Solicitação

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|----------|-----------|
| `job_id` | string | Sim | ID de job único |
| `func_name` | string | Sim | Nome da função a executar |
| `trigger` | string | Sim | Tipo de trigger (`cron`, `interval`, `date`) |
| `trigger_args` | object | Sim | Argumentos de trigger (`hour`, `minute`, `day_of_week`, etc.) |

### Exemplo

```bash
curl -X POST "http://localhost:5100/api/scheduler/jobs" \
     -H "X-Requested-With: XMLHttpRequest" \
     -H "Content-Type: application/json" \
     -d '{
       "job_id": "custom_cleanup",
       "func_name": "thumbnail_cleanup",
       "trigger": "cron",
       "trigger_args": { "hour": 6, "minute": 30 }
     }'
```

```json
{
  "ok": true,
  "data": {
    "job_id": "custom_cleanup",
    "next_run": "2026-03-16T06:30:00"
  }
}
```

## DELETE /api/scheduler/jobs/\<id\>

Remove um job. Sujeito a rate limiting de tier **DESTRUCTIVE**.

### Parâmetros de Caminho

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `id` | string | ID do job |

### Exemplo

```bash
curl -X DELETE "http://localhost:5100/api/scheduler/jobs/custom_cleanup" \
     -H "X-Requested-With: XMLHttpRequest"
```

```json
{
  "ok": true,
  "data": { "removed": "custom_cleanup" }
}
```

## POST /api/scheduler/jobs/\<id\>/pause

Pausa um job.

### Exemplo

```bash
curl -X POST "http://localhost:5100/api/scheduler/jobs/db_vacuum/pause" \
     -H "X-Requested-With: XMLHttpRequest"
```

```json
{
  "ok": true,
  "data": { "job_id": "db_vacuum", "paused": true }
}
```

## POST /api/scheduler/jobs/\<id\>/resume

Retoma um job pausado.

### Exemplo

```bash
curl -X POST "http://localhost:5100/api/scheduler/jobs/db_vacuum/resume" \
     -H "X-Requested-With: XMLHttpRequest"
```

```json
{
  "ok": true,
  "data": { "job_id": "db_vacuum", "paused": false }
}
```

## POST /api/scheduler/jobs/\<id\>/trigger

Dispara execução imediata de um job. Sujeito a rate limiting de tier **WRITE**.

### Exemplo

```bash
curl -X POST "http://localhost:5100/api/scheduler/jobs/db_vacuum/trigger" \
     -H "X-Requested-With: XMLHttpRequest"
```

```json
{
  "ok": true,
  "data": { "job_id": "db_vacuum", "triggered": true }
}
```

## GET /api/scheduler/history

Retorna histórico de execução em ordem mais novo-primeiro (máx 100 entradas).

### Resposta

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `ok` | boolean | Flag de sucesso |
| `data.history` | array | Array de entradas de histórico de execução |
| `data.history[].job_id` | string | ID do job |
| `data.history[].executed_at` | string | Timestamp de execução (ISO 8601) |
| `data.history[].status` | string | Resultado (`success`, `error`) |
| `data.history[].duration_ms` | number | Duração de execução (milissegundos) |
| `data.history[].error` | string\|null | Mensagem de erro (apenas em falha) |

### Exemplo

```bash
curl "http://localhost:5100/api/scheduler/history"
```

```json
{
  "ok": true,
  "data": {
    "history": [
      {
        "job_id": "db_vacuum",
        "executed_at": "2026-03-15T03:00:00",
        "status": "success",
        "duration_ms": 1234
      }
    ]
  }
}
```
