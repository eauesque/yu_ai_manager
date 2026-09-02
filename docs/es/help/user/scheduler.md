# Programador de tareas

## Resumen

El programador de tareas es una funcionalidad que ejecuta automáticamente tareas periódicas como el mantenimiento de la base de datos o el sondeo de servicios externos. Un scheduler en segundo plano basado en APScheduler gestiona los trabajos con disparadores cron / interval.

Desde la página del programador (`/scheduler`) de la WebUI es posible listar, añadir, eliminar, pausar y ejecutar inmediatamente los trabajos.

## Configuración

El programador está activado por defecto. Puede controlarlo con `scheduler.enabled` en `config.json`:

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

Los trabajos descritos en `config.json` se registran automáticamente al arrancar el servidor. Los trabajos añadidos desde la WebUI solo son válidos durante la sesión del servidor (se pierden al reiniciar).

## Lista de trabajos integrados

### Mantenimiento de la base de datos

| ID del trabajo | Descripción | Frecuencia recomendada |
|-----------|------|---------|
| `db_vacuum` | Ejecuta SQLite VACUUM para recuperar espacio no utilizado | Semanal |
| `db_integrity_check` | Verifica la integridad de la base de datos con `PRAGMA integrity_check` | Diaria |
| `db_backup` | Crea una copia de seguridad de la base de datos (vía builtin-backup extension) | Diaria |

### Gestión de caché e índices

| ID del trabajo | Descripción | Frecuencia recomendada |
|-----------|------|---------|
| `thumbnail_cleanup` | Elimina los archivos de caché de miniaturas caducados | Diaria |
| `prune_unused_tags` | Elimina registros de etiquetas huérfanas no vinculadas a archivos | Semanal o mensual |
| `refresh_monthly_stats` | Actualiza la caché precalculada de estadísticas mensuales | Diaria |
| `rebuild_groups_index` | Reconstruye la caché del índice de grupos de carpetas / archivos | Semanal |

### Integración con servicios externos

| ID del trabajo | Descripción | Frecuencia recomendada |
|-----------|------|---------|
| `github_issue_poll` | Sondea la API de GitHub e incorpora nuevos Issues a la cola local | 5 min a 1 h |
| `bsky_notification_poll` | Sondea la API de Bluesky y obtiene las nuevas notificaciones | 5 min a 1 h |

## Configuración de los disparadores

### Disparador cron

Se ejecuta en una hora / día de la semana / fecha específica. La forma de especificación es similar a cron de Unix.

| Parámetro | Ejemplos de valor | Descripción |
|-----------|--------|------|
| `hour` | `3`, `*/6`, `1,13` | Hora (0-23). `*` para cada hora |
| `minute` | `0`, `30`, `0,30` | Minuto (0-59). `*` para cada minuto |
| `day` | `1`, `15`, `1,15` | Día (1-31). `*` para cada día |
| `day_of_week` | `sun`, `mon-fri`, `0-4` | Día de la semana. `*` para todos los días |

**Ejemplo**: Ejecutar cada día 1 y 15 a las 2:30 de la madrugada

```json
{ "trigger": "cron", "day": "1,15", "hour": 2, "minute": 30 }
```

### Disparador interval

Se ejecuta repetidamente a un intervalo fijo.

| Parámetro | Ejemplos de valor | Descripción |
|-----------|--------|------|
| `hours` | `2` | Intervalo en horas |
| `minutes` | `30` | Intervalo en minutos |

**Ejemplo**: Ejecutar cada 30 minutos

```json
{ "trigger": "interval", "minutes": 30 }
```

## Cómo usar la WebUI

### Lista de trabajos

Al abrir la página del programador se muestra la lista de trabajos registrados. Se puede comprobar el estado (activo / pausado), la configuración del disparador y la próxima hora de ejecución.

### Añadir un trabajo

1. Haga clic en el botón **Añadir trabajo**
2. Introduzca el ID del trabajo (nombre único)
3. Seleccione la función a ejecutar en el desplegable
4. Seleccione el tipo de disparador (cron / interval)
5. Introduzca los parámetros de la planificación (se admite `*` como comodín)
6. Haga clic en **Añadir**

### Operaciones sobre trabajos

- **Ejecutar ahora**: ejecuta el trabajo inmediatamente una vez, fuera de la planificación
- **Pausar / Reanudar**: detiene o reactiva temporalmente la ejecución periódica
- **Eliminar**: elimina el trabajo por completo (los de `config.json` se restauran en el siguiente arranque)

### Historial de ejecución

En la parte inferior de la página se muestra el historial reciente (hasta 50 entradas). Puede consultar el estado de éxito/fallo y el mensaje de resultado. Al completarse una ejecución, se actualiza en tiempo real mediante SSE.

## Herramientas MCP

Los clientes MCP (como Claude Desktop) pueden operar el programador:

| Herramienta | Descripción |
|--------|------|
| `get_scheduler_status` | Obtiene el estado de operación del programador |
| `list_scheduled_jobs` | Obtiene la lista de trabajos registrados |
| `trigger_scheduled_job` | Ejecuta un trabajo inmediatamente |
| `pause_scheduled_job` | Pausa un trabajo |
| `resume_scheduled_job` | Reanuda un trabajo |
| `get_scheduler_history` | Obtiene el historial de ejecución |

## Consejos

- Los **trabajos de sondeo externos** (`github_issue_poll`, `bsky_notification_poll`) se adaptan mejor al disparador interval. Al fijarlos con cron, los intervalos de sondeo pueden separarse demasiado
- **`db_vacuum`** toma un bloqueo de escritura, se recomienda programarlo en horario nocturno con poco acceso
- **`db_backup`** respeta la configuración de cooldown de la extensión builtin-backup. Aunque se configure con un interval corto, se omite durante el periodo de cooldown
- El **historial de ejecución se conserva en memoria** (máximo 100 entradas). Se borra al reiniciar el servidor
