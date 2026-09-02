# API de Puerta de Seguridad del Agente

APIs para gestionar controles de seguridad de agentes AI. Proporciona Kill Switch, Circuit Breaker, Budget, Action Journal, Approval Gate, Scope Fence, Auto-Approve, Tool Classification, Undo, Anomaly Detection y funcionalidad de Audit Bureau.

Todos los endpoints POST/DELETE requieren el encabezado `X-Requested-With` (excepto cuando se utiliza Bearer API Key).

---

## Kill Switch

### POST /api/agent/kill

Activar Kill Switch para detener inmediatamente todas las operaciones del agente.

#### Límite de velocidad

WRITE

#### Solicitud

```json
{
  "reason": "Manual kill via API"
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `reason` | string | No | Razón para detener. Por defecto: `"Manual kill via API"` |

#### Respuesta

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

Desactivar Kill Switch para reanudar operaciones del agente.

#### Límite de velocidad

WRITE

#### Solicitud

Ninguna (cuerpo vacío)

#### Respuesta

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

Obtener estado unificado de Kill Switch, Circuit Breaker y Budget.

#### Parámetros

Ninguno

#### Respuesta

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

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `kill_switch` | object | Estado detallado de Kill Switch |
| `circuit_breaker` | object | Estado detallado de Circuit Breaker. Devuelve `{"enabled": false, "state": "unknown"}` en error |
| `budget` | object | Estado detallado de Budget. Devuelve objeto vacío en error |
| `killed` | boolean | Indicador de Kill Switch activo (nivel superior para compatibilidad hacia atrás) |
| `reason` | string | Razón de Kill Switch (compatibilidad hacia atrás) |
| `killed_at` | string | Tiempo de activación de Kill Switch (compatibilidad hacia atrás) |

---

## Circuit Breaker

### GET /api/agent/circuit-breaker

Obtener estado de Circuit Breaker.

#### Parámetros

Ninguno

#### Respuesta

```json
{
  "enabled": true,
  "state": "closed",
  "failure_count": 0,
  "threshold": 5
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `enabled` | boolean | Si Circuit Breaker está habilitado |
| `state` | string | Estado: `"closed"` (normal), `"open"` (accionado), `"half_open"` (probando) |
| `failure_count` | int | Recuento de fallos consecutivos |
| `threshold` | int | Umbral de recuento de fallos para abrir |

### POST /api/agent/circuit-breaker/reset

Restablecer Circuit Breaker al estado cerrado.

#### Límite de velocidad

WRITE

#### Solicitud

Ninguna (cuerpo vacío)

#### Respuesta

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

## Budget

### GET /api/agent/budget

Obtener presupuesto restante para la sesión actual.

#### Parámetros

Ninguno

#### Respuesta

```json
{
  "session_id": "abc123",
  "used": 10,
  "limit": 100,
  "remaining": 90
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `session_id` | string | ID de sesión |
| `used` | int | Número de acciones consumidas |
| `limit` | int | Máximo de acciones permitidas |
| `remaining` | int | Acciones restantes |

### POST /api/agent/budget/reset

Restablecer el contador de presupuesto.

#### Límite de velocidad

WRITE

#### Solicitud

Ninguna (cuerpo vacío)

#### Respuesta

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

## Action Journal

### GET /api/agent/journal

Buscar en Action Journal. Devuelve historial de acciones ejecutadas por agentes.

#### Parámetros

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `tool_name` | string | No | Filtrar por nombre de herramienta |
| `status` | string | No | Filtrar por estado |
| `session_id` | string | No | Filtrar por ID de sesión |
| `limit` | int | No | Máx resultados (por defecto: 50, máx: 200) |
| `offset` | int | No | Desplazamiento (por defecto: 0) |

#### Respuesta

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

Obtener estadísticas de Action Journal.

#### Parámetros

Ninguno

#### Respuesta

```json
{
  "total_entries": 150,
  "by_tool": {"add_tags": 50, "delete_tags": 30, "scan": 70},
  "by_status": {"completed": 140, "failed": 10}
}
```

---

## Approval Gate

### GET /api/agent/approval

Obtener lista de solicitudes de aprobación pendientes.

#### Parámetros

Ninguno

#### Respuesta

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

Responder a una solicitud de aprobación.

#### Límite de velocidad

WRITE

#### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `request_id` | string | ID de solicitud (parámetro de ruta) |

#### Solicitud

```json
{
  "decision": "allow"
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `decision` | string | Sí | `"allow"` (permitir), `"deny"` (rechazar), `"always_allow"` (permitir siempre) |

#### Respuesta

```json
{
  "ok": true,
  "request_id": "req_abc123",
  "decision": "allow"
}
```

#### Errores

- `400`: `decision` no es uno de `allow`/`deny`/`always_allow`
- `404`: Solicitud no encontrada o ya respondida

### GET /api/agent/approval/history

Obtener historial de aprobaciones.

#### Parámetros

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `limit` | int | No | Máx resultados (por defecto: 50, máx: 200) |

#### Respuesta

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

## Scope Fence

### GET /api/agent/scope

Obtener estado de Scope Fence para todas las sesiones.

#### Parámetros

Ninguno

#### Respuesta

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

Obtener alcance para una sesión específica.

#### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `session_id` | string | ID de sesión (parámetro de ruta) |

#### Respuesta

```json
{
  "preset": "tagger",
  "denied": ["purge_deleted", "hard_delete"],
  "name": "Tagger Bot",
  "expires_at": "2026-03-22T14:00:00"
}
```

#### Errores

- `404`: Alcance de sesión no encontrado

### POST /api/agent/scope/\<session_id\>

Establecer alcance de sesión.

#### Límite de velocidad

WRITE

#### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `session_id` | string | ID de sesión (parámetro de ruta) |

#### Solicitud

```json
{
  "preset": "tagger",
  "denied": ["purge_deleted"],
  "name": "Tagger Bot",
  "duration_hours": 2.0
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `preset` | string | No | Nombre predeterminado: `"read_only"`, `"tagger"`, `"organizer"`, `"full_access"` |
| `denied` | string[] | No | Lista de nombres de herramientas negadas |
| `name` | string | No | Nombre mostrado para el alcance |
| `duration_hours` | number | No | Expiración de alcance en horas |

#### Respuesta

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

#### Errores

- `400`: `denied` no es una lista

### DELETE /api/agent/scope/\<session_id\>

Eliminar un alcance de sesión.

#### Límite de velocidad

WRITE

#### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `session_id` | string | ID de sesión (parámetro de ruta) |

#### Respuesta

```json
{
  "ok": true
}
```

---

## Reglas de Auto-Aprobar

### GET /api/agent/auto-approve

Obtener lista de reglas de auto-aprobación.

#### Parámetros

Ninguno

#### Respuesta

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

Agregar una regla de auto-aprobación.

#### Límite de velocidad

WRITE

#### Solicitud

```json
{
  "tool": "add_tags",
  "conditions": {"max_count": 10}
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `tool` | string | Sí | Nombre de herramienta de destino |
| `conditions` | object | No | Condiciones para auto-aprobación. Omitir para aprobación incondicional |

#### Respuesta

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

#### Errores

- `400`: `tool` no está especificado
- `400`: `conditions` no es un diccionario

### DELETE /api/agent/auto-approve/\<index\>

Eliminar una regla de auto-aprobación.

#### Límite de velocidad

WRITE

#### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `index` | int | Índice de regla (parámetro de ruta) |

#### Respuesta

```json
{
  "ok": true
}
```

#### Errores

- `404`: Regla no encontrada

---

## Clasificación de Herramientas

### GET /api/agent/tool-levels

Obtener información de clasificación de herramientas. Cuando se especifica el parámetro `tool`, devuelve el nivel para esa herramienta específica. De lo contrario, devuelve un resumen de todas las herramientas y cualquier anulación.

#### Parámetros

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `tool` | string | No | Nombre de herramienta. Si se especifica, devuelve solo el nivel de esa herramienta |

#### Respuesta (herramienta específica)

```json
{
  "tool": "purge_deleted",
  "level": "destructive"
}
```

#### Respuesta (todas las herramientas)

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

## Deshacer

### POST /api/agent/undo/\<journal_id\>

Deshacer una acción registrada.

#### Límite de velocidad

WRITE

#### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `journal_id` | int | ID de entrada del diario (parámetro de ruta) |

#### Respuesta

```json
{
  "ok": true,
  "journal_id": 1,
  "undone_action": "add_tags"
}
```

#### Errores

- `400`: Deshacer falló (acción no reversible, ya deshecha, etc.)

### GET /api/agent/undoable

Obtener lista de acciones reversibles.

#### Parámetros

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `session_id` | string | No | Filtrar por ID de sesión |
| `limit` | int | No | Máx resultados (por defecto: 50, máx: 200) |

#### Respuesta

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

## Anomaly Detection

### GET /api/agent/anomaly

Obtener estado de Anomaly Detection.

#### Parámetros

Ninguno

#### Respuesta

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

Obtener alertas de Anomaly Detection.

#### Parámetros

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `limit` | int | No | Máx resultados (por defecto: 50, máx: 200) |

#### Respuesta

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

Restablecer historial de Anomaly Detection y alertas.

#### Límite de velocidad

WRITE

#### Solicitud

Ninguna (cuerpo vacío)

#### Respuesta

```json
{
  "ok": true
}
```

---

## Audit Bureau

### GET /api/agent/audit

Obtener estado de Audit Bureau.

#### Parámetros

Ninguno

#### Respuesta

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

Buscar en Audit Log.

#### Parámetros

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `event_type` | string | No | Filtrar por tipo de evento |
| `severity` | string | No | Filtrar por severidad |
| `source` | string | No | Filtrar por fuente |
| `unacknowledged` | string | No | Establecer en `"1"` o `"true"` para devolver solo entradas no reconocidas |
| `limit` | int | No | Máx resultados (por defecto: 50, máx: 200) |
| `offset` | int | No | Desplazamiento (por defecto: 0) |

#### Respuesta

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

Marcar una entrada de registro de auditoría como reconocida por el usuario.

#### Límite de velocidad

WRITE

#### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `audit_id` | int | ID de entrada de registro de auditoría (parámetro de ruta) |

#### Respuesta

```json
{
  "ok": true,
  "audit_id": 1
}
```

#### Errores

- `404`: Entrada no encontrada o ya reconocida

### POST /api/agent/audit/report

Generar manualmente un informe periódico de Audit Bureau.

#### Límite de velocidad

WRITE

#### Solicitud

```json
{
  "hours": 24
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `hours` | int | No | Período de informe en horas. Por defecto: 24, máx: 720 |

#### Respuesta

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
