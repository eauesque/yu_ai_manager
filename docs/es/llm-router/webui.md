# WebUI del LLM Router

Un panel de administración accesible en `/llm-router`. Permite verificar el estado de los backends registrados y habilitarlos/deshabilitarlos.

---

## Diseño de la página

```
┌─────────────────────────────────────┐
│  🤖 LLM Router          [Refresh All] │
├─────────┬─────────┬────────┬─────────┤
│Backends │ Enabled │ Models │ Aliases │  ← Summary cards
├─────────┴─────────┴────────┴─────────┤
│  Backends table                      │
├───────────────────────────────────────┤
│  Routing Aliases table               │
└───────────────────────────────────────┘
```

### Tarjetas de resumen (4)

| Tarjeta | Contenido |
|---|---|
| **Backends** | Número total de backends registrados en el catálogo |
| **Enabled** | Número de backends que no están deshabilitados |
| **Models** | Número total de modelos expuestos por todos los backends |
| **Routing aliases** | Número de alias definidos en el archivo de configuración |

Los valores de las tarjetas se renderizan automáticamente al cargar la página obteniendo `/api/llm_router/status`.

---

## Tabla de Backends

Cada fila corresponde a un backend físico individual (por ejemplo, una instancia de Ollama).

### Descripciones de columnas

| Columna | Descripción |
|---|---|
| **Alias** | Un nombre corto único que identifica el backend (por ejemplo, `ollama-mac`, `mdns-pi5-hailo`). Se usa como clave para la configuración de enrutamiento y resolución de alias |
| **Base URL** | La URL base del punto final compatible con OpenAI del backend (por ejemplo, `http://192.168.1.10:11434`) |
| **Status** | Estado de conectividad del backend. Ver detalles a continuación |
| **SLO** | Estado de carga de recursos del backend (`vision_idle` / `vision_active` / `unknown`). Se usa para backends Hailo Vision |
| **Models** | Número de modelos recuperados en la última sonda. Puede ser expandible para mostrar una lista detallada según la implementación |
| **Last Seen** | Fecha y hora de la última respuesta exitosa (ISO 8601). `null` si nunca se ha recibido una respuesta exitosa |
| **Actions** | Botones de acción por backend (ver a continuación) |

### Valores de estado

| Valor | Significado |
|---|---|
| `ready` | La última sonda fue exitosa y se recuperó la lista de modelos |
| `unreachable` | Ocurrió un timeout de conexión o error |
| `unknown` | Aún no se ha ejecutado ninguna sonda (por ejemplo, justo después del inicio) |
| `probing` | Una sonda se está ejecutando actualmente (puede aparecer brevemente en la UI durante una actualización) |

> **Consejo**: Los backends `unreachable` se excluyen del enrutamiento pero permanecen en el catálogo. Después de la recuperación de la red, ejecute Refresh All o una actualización individual para restaurarlos a `ready`.

### Valores de SLO

| Valor | Significado |
|---|---|
| `vision_idle` | La tarea de visión está inactiva. La carga del LLM es baja |
| `vision_active` | Se está ejecutando una tarea de visión. El enrutador LLM puede priorizar otros backends |
| `unknown` | La información de SLO no está disponible (backend no Hailo, o la recuperación falló) |

---

## Botón Refresh All

Haga clic en **Refresh All** en la esquina superior derecha para forzar una sonda en todos los backends, actualizando sus listas de modelos y estados.

- El botón se deshabilita durante la ejecución y la página se reenderiza al completarse
- Comportamiento interno: Llama a `POST /api/llm_router/refresh` (sin body) para ejecutar `discover_all` para todos los backends
- Las actualizaciones de backend individuales pueden estar disponibles a través de un botón Refresh en la columna Actions (depende de la implementación)

---

## Deshabilitación / Habilitación de backends individuales

### Pasos

1. Mire la columna **Actions** en la tabla de backends
2. Haga clic en el botón **Disable** en la fila del backend que desea deshabilitar
3. El botón cambia a **Enable** y la fila se vuelve gris
4. Para rehabilitar, haga clic en **Enable**

### Comportamiento y persistencia

- Los cambios se reflejan inmediatamente en el catálogo en memoria
- Simultáneamente, se realiza una escritura atómica en `data/llm_router_state.json`

  ```json
  {
    "version": 1,
    "disabled_aliases": ["ollama-slow", "mdns-pi5"]
  }
  ```

- El estado deshabilitado se conserva entre reinicios de aplicación
- Si un backend descubierto por mDNS fue deshabilitado antes del inicio, el estado deshabilitado se aplica automáticamente después del descubrimiento (mecanismo `_pending_disabled`)
- Si la escritura falla, el estado en memoria se revierte para evitar inconsistencia con el disco

### Comportamiento de backends deshabilitados

- Excluidos del enrutamiento en puntos finales compatibles con OpenAI como `/v1/chat/completions`
- El enrutamiento directo a un backend deshabilitado devuelve `503 Service Unavailable`
- Los backends deshabilitados aún aparecen en la tabla WebUI (para visibilidad de estado y rehabilitar)

---

## Tabla de alias de enrutamiento

Muestra la asignación entre nombres de modelo lógicos e ID de modelo físicos como se define en el archivo de configuración.

| Columna | Descripción |
|---|---|
| **Alias** | El nombre lógico que los clientes especifican en el parámetro `model` (por ejemplo, `default-llm`, `fast-chat`) |
| **Physical Model** | El ID de modelo físico que realmente procesa la solicitud (formato: `backend-alias/model-name`, por ejemplo, `ollama-mac/qwen2.5:7b`) |

### Rol de los alias

Los alias le permiten cambiar backends o modelos sin cambiar el código del cliente.

- Los clientes envían solicitudes usando un nombre lógico como `"model": "default-llm"`
- El LLM Router resuelve `default-llm → ollama-mac/qwen2.5:7b` y redirige la solicitud
- Al migrar un backend a otra máquina, simplemente cambie el destino del alias

Los alias se definen estáticamente en el archivo de configuración, y la WebUI los muestra en modo de solo lectura. Los cambios requieren editar el archivo de configuración y reiniciar la aplicación.

---

## Operaciones comunes

### Cuando un backend es inaccesible

1. Verifique que el servicio backend (Ollama, etc.) esté en ejecución
2. Ejecute **Refresh All** o una actualización individual
3. Si el problema persiste, verifique los detalles del error en la columna `last_error` (o respuesta API)

### Deshabilitación permanente de un backend descubierto por mDNS

1. Haga clic en **Disable** en la columna Actions del backend objetivo
2. El alias se guarda en `data/llm_router_state.json`, por lo que permanece deshabilitado incluso después del redescubrimiento

### Detención temporal de la carga en un backend específico

Use **Disable** para excluirlo inmediatamente del enrutamiento, luego **Enable** para restaurarlo cuando haya terminado. No se requiere reinicio.
