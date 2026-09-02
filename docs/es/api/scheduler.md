# API del Planificador

API de gestión para el planificador de tareas. Permite verificar el estado, agregar/eliminar trabajos, pausar/reanudar, activar ejecución inmediata y recuperar historial de ejecución.

## Configuración

Habilite el planificador y configure los horarios de trabajo integrados en `config.json`:

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

### Trabajos Integrados

| ID de Trabajo | Descripción | Horario Predeterminado |
|--------|-------------|-----------------|
| `db_vacuum` | Base de datos VACUUM (recuperar espacio) | Cada domingo a las 03:00 |
| `db_integrity_check` | Comprobación de integridad de la base de datos | Diariamente a las 04:00 |
| `thumbnail_cleanup` | Limpieza de caché de miniaturas | Diariamente a las 05:00 |
| `github_issue_poll` | Sondeo de problemas de GitHub | No configurado (agregar a través de WebUI) |
| `bsky_notification_poll` | Sondeo de notificaciones de Bluesky | No configurado (agregar a través de WebUI) |
| `prune_unused_tags` | Podar etiquetas no utilizadas | No configurado (agregar a través de WebUI) |
| `refresh_monthly_stats` | Actualizar caché de estadísticas mensuales | No configurado (agregar a través de WebUI) |
| `rebuild_groups_index` | Reconstruir índice de grupos | No configurado (agregar a través de WebUI) |
| `db_backup` | Copia de seguridad de la base de datos | No configurado (agregar a través de WebUI) |

## GET /api/scheduler/status

Devuelve el estado del planificador e información sobre todos los trabajos.

### Respuesta

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `ok` | boolean | Bandera de éxito |
| `data.running` | boolean | Si el planificador está en ejecución |
| `data.jobs` | array | Lista de trabajos (incluidos tiempos de próxima ejecución) |

### Ejemplo

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

Devuelve la lista de trabajos con tiempos de `next_run`.

### Respuesta

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `ok` | boolean | Bandera de éxito |
| `data.jobs` | array | Array de objetos de trabajo |
| `data.jobs[].job_id` | string | ID de trabajo |
| `data.jobs[].func_name` | string | Nombre de función a ejecutar |
| `data.jobs[].trigger` | string | Tipo de activador (`cron`, `interval`, `date`) |
| `data.jobs[].next_run` | string | Tiempo de próxima ejecución programada (ISO 8601) |
| `data.jobs[].paused` | boolean | Si el trabajo está pausado |

### Ejemplo

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

Agregar un trabajo personalizado.

### Cuerpo de Solicitud

| Campo | Tipo | Requerido | Descripción |
|-------|------|----------|-------------|
| `job_id` | string | Sí | ID de trabajo único |
| `func_name` | string | Sí | Nombre de función a ejecutar |
| `trigger` | string | Sí | Tipo de activador (`cron`, `interval`, `date`) |
| `trigger_args` | object | Sí | Argumentos del activador (`hour`, `minute`, `day_of_week`, etc.) |

### Ejemplo

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

Eliminar un trabajo. Sujeto a límite de velocidad de nivel **DESTRUCTIVE**.

### Parámetros de Ruta

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `id` | string | ID de trabajo |

### Ejemplo

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

Pausar un trabajo.

### Ejemplo

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

Reanudar un trabajo pausado.

### Ejemplo

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

Activar ejecución inmediata de un trabajo. Sujeto a límite de velocidad de nivel **WRITE**.

### Ejemplo

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

Devuelve el historial de ejecución en orden más reciente primero (máx. 100 entradas).

### Respuesta

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `ok` | boolean | Bandera de éxito |
| `data.history` | array | Array de entradas de historial de ejecución |
| `data.history[].job_id` | string | ID de trabajo |
| `data.history[].executed_at` | string | Timestamp de ejecución (ISO 8601) |
| `data.history[].status` | string | Resultado (`success`, `error`) |
| `data.history[].duration_ms` | number | Duración de ejecución (milisegundos) |
| `data.history[].error` | string\|null | Mensaje de error (solo en caso de fallo) |

### Ejemplo

```bash
curl "http://localhost:5100/api/scheduler/history"
```

```json
{
  "ok": true,
  "data": {
    "history": [
      {
        "job_id": "db_integrity_check",
        "executed_at": "2026-03-15T04:00:02",
        "status": "success",
        "duration_ms": 1234,
        "error": null
      },
      {
        "job_id": "thumbnail_cleanup",
        "executed_at": "2026-03-15T05:00:01",
        "status": "success",
        "duration_ms": 567,
        "error": null
      }
    ]
  }
}
```

## Eventos SSE

Los eventos relacionados con el planificador se entregan a través del motor compartido SSE.

| Evento | Datos | Descripción |
|-------|------|-------------|
| `scheduler.job_executed` | `{ job_id, result }` | Ejecución del trabajo completada |
| `scheduler.job_error` | `{ job_id, error }` | Error de ejecución del trabajo |

```javascript
window.sseSubscribe('scheduler.job_executed', (data) => {
  console.log(`Job ${data.job_id} completed: ${data.result}`);
});
```

## Herramientas MCP

| Herramienta | Descripción |
|------|-------------|
| `get_scheduler_status` | Obtener estado de ejecución del planificador |
| `list_scheduled_jobs` | Listar trabajos registrados |
| `trigger_scheduled_job` | Activar ejecución inmediata del trabajo |
| `pause_scheduled_job` | Pausar un trabajo |
| `resume_scheduled_job` | Reanudar un trabajo |
| `get_scheduler_history` | Obtener historial de ejecución |

## Limitación de Velocidad

| Endpoint | Método | Nivel |
|----------|--------|------|
| `/api/scheduler/status` | GET | READ (ilimitado) |
| `/api/scheduler/jobs` | GET | READ (ilimitado) |
| `/api/scheduler/jobs` | POST | WRITE (~120 req/min) |
| `/api/scheduler/jobs/<id>` | DELETE | DESTRUCTIVE (~12 req/min) |
| `/api/scheduler/jobs/<id>/pause` | POST | WRITE (~120 req/min) |
| `/api/scheduler/jobs/<id>/resume` | POST | WRITE (~120 req/min) |
| `/api/scheduler/jobs/<id>/trigger` | POST | WRITE (~120 req/min) |
| `/api/scheduler/history` | GET | READ (ilimitado) |
