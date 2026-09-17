# Gestión de Fleet (Fleet Admin)

La función Fleet Admin de LAN Cowork es una función para gestionar centralmente múltiples nodos yu-ai-manager en la red.

## Descripción general

- **Recopilación de información del dispositivo**: Agregación centralizada de CPU / RAM / GPU / disco / versión / tiempo de actividad de cada nodo
- **Visualización de registros remotos**: Transmisión en vivo de registros de cualquier peer desde la UI del nodo central mediante SSE
- **Distribución de actualización de versión**: Instructar desde el centro a pares específicos `git pull --ff-only` + reinicio elegante

## Requisitos previos

- Extensión LAN Cowork habilitada (`extensions["builtin-lan-cowork"].enabled = true`)
- Emparejamiento completado entre pares
- Clonado como repositorio git (si usa función de actualización)
- `psutil>=5.9` instalado en entorno virtual Python

## Configuración

### Configuración del nodo jefe

Agregue lo siguiente a `config.json`:

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "fleet": {
        "chief": true,
        "allow_remote_update": true,
        "allow_update_from": [
          "<peer_id emparejado>"
        ],
        "allow_log_stream_from": [
          "<peer_id emparejado>"
        ],
        "allowed_branches": [
          "main"
        ],
        "timings": {
          "chief_observation_sec": 25,
          "peers_poll_interval_sec": 30,
          "heartbeat_timeout_sec": 60,
          "update_job_timeout_sec": 600,
          "postcheck_timeout_sec": 180
        }
      }
    }
  }
}
```

### Configuración del nodo normal

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "fleet": {
        "chief": false,
        "allow_remote_update": true,
        "allow_update_from": [
          "<peer_id del jefe>"
        ],
        "allow_log_stream_from": [
          "<peer_id del jefe>"
        ],
        "allowed_branches": [
          "main"
        ]
      }
    }
  }
}
```

## Acceso a UI de gestión de Fleet

Acceda a `/ext/lan_cowork/fleet/ui` desde el navegador del nodo jefe.

En nodos normales, esta URL devuelve 404.

## Funcionalidad de pestañas

### Pestaña Descripción general

- Visualización de tarjeta de todos los nodos (con barras de uso de CPU / RAM / GPU / Disco)
- Indicación de estado en línea / desconectado / fallo de obtención de información
- Distintivo `[CHIEF]` en nodo jefe
- Actualización automática cada 30 segundos + botón de actualización manual
- Pancarta de advertencia cuando se detectan múltiples jefes

### Pestaña Registros

- Visualización en vivo de registros de cualquier peer mediante SSE (estilo tail -f)
- Filtro de nivel (DEBUG / INFO / WARNING / ERROR)
- Cuadro de búsqueda (filtro del lado del cliente)
- Desplazamiento automático ON/OFF
- Pausa / Reanudar

### Pestaña Actualización

- Tabla comparativa de versión / commit git / rama
- Botón "Pull & Restart" para nodos individuales
- Actualización por lotes de múltiples nodos (dispatch)
- Indicación de progreso (precheck → fetching → pulling → restarting → online)
- El jefe mismo está excluido de actualización por lotes (solo botón individual)

## Seguridad

### Estructura de autorización de dos capas

1. **Emparejamiento (verificación de identidad)**: Identificar "quién" con token Bearer
2. **allowlist (permisos)**: Permitir explícitamente por operación

Emparejado = todos los permisos, no es así.

### Ejemplo de configuración de allowlist

```json
"allow_update_from": [
  "abc123def456",
  {"peer_id": "def456abc789"}
]
```

- Se pueden usar ambos formatos cadena y `{peer_id: ...}`
- El peer_id propio se agrega automáticamente (no es necesario configurar)

## Degradación automática del jefe

Si se inician múltiples nodos con `chief = true` en la misma red, el nodo iniciado posteriormente se degrada automáticamente (después de observar `chief_observation_sec` segundos).

Para volver a ser jefe después de degradar, se requiere reinicio después de cambiar configuración (sin ascenso automático).

## Restricciones de actualización git

- Solo se utiliza `git pull --ff-only` (no se usa merge/rebase)
- Si no puede hacer avance rápido, falla inmediatamente `failed` (árbol de trabajo no se modifica)
- Se rechaza actualización si árbol de trabajo está dirty

## Solución de problemas

| Síntoma | Causa | Acción |
|---|---|---|
| `/fleet/ui` es 404 | `chief = true` no configurado | Verifique config.json y reinicie |
| `/fleet/info` es 500 | psutil no instalado | `uv pip install psutil>=5.9` |
| Error `git_not_available` | git no existe o PATH incorrecto | Verifique instalación de git |
| Timeout `postcheck_online` después de actualizar | Reinicio tardó más de 3 minutos | Extienda `postcheck_timeout_sec` |
| Pancarta de múltiples jefes no desaparece | Proceso jefe anterior persistente | Reinicie jefe anterior |

## Referencia de API

### Común a todos los nodos

| Endpoint | Descripción |
|---|---|
| `GET /ext/lan_cowork/fleet/info` | Información del dispositivo (autenticación Bearer requerida) |
| `GET /ext/lan_cowork/fleet/logs/stream` | SSE de registro propio (autorización allowlist) |
| `POST /ext/lan_cowork/fleet/update` | git pull + reinicio (autorización allowlist) |
| `GET /ext/lan_cowork/fleet/update/status` | Consultar estado de trabajo update |

### Solo nodo jefe

| Endpoint | Descripción |
|---|---|
| `GET /ext/lan_cowork/fleet/peers` | Agregación de información de todos los peers |
| `GET /ext/lan_cowork/fleet/logs/stream?peer_id=X` | Retransmisión SSE de registro de peer especificado |
| `POST /ext/lan_cowork/fleet/update/dispatch` | Actualización por lotes a múltiples peers |
| `GET /ext/lan_cowork/fleet/update/dispatch/status` | Consultar progreso de dispatch |
| `GET /ext/lan_cowork/fleet/ui` | UI de gestión de Fleet |
