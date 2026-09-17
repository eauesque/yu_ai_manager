# API de Escaneo

APIs para escaneo de archivos y gestión de raíz de escaneo.

## Control de Escaneo

### POST /api/scan/start

Iniciar un escaneo.

### Solicitud

```json
{
  "root_indices": [0, 1],
  "force": false
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `root_indices` | int[] | Índices de raíces a escanear (omitir para todas las raíces) |
| `force` | bool | Re-escanear archivos existentes |

### Respuesta

```json
{
  "ok": true,
  "message": "Scan started"
}
```

### GET /api/scan/status

Recuperar progreso de escaneo.

### Respuesta

```json
{
  "scanning": true,
  "progress": 45,
  "total": 1500,
  "current_file": "/images/output/00042.png",
  "errors": 0,
  "started_at": 1709500000
}
```

### POST /api/scan/cancel

Cancelar un escaneo en ejecución.

### GET /api/scan/interrupted

Recuperar información sobre un escaneo interrumpido.

### POST /api/scan/resume

Reanudar un escaneo interrumpido.

### POST /api/scan/dismiss

Descartar el estado de escaneo interrumpido.

## CLI del Trabajador de Escaneo

Desde v3.27.0, los escaneos se ejecutan en un proceso separado (trabajador).
El trabajador se puede controlar directamente desde el CLI además de la API WebUI.

```bash
# Iniciar un escaneo
python -m core.scan.scan_worker start --db ./tags.db --root /path/to/images [--scan-zips] [--force] [--resume]

# Detener un escaneo (SIGTERM -> apagado elegante)
python -m core.scan.scan_worker stop

# Verificar estado
python -m core.scan.scan_worker status
```

### Archivos IPC

| Archivo | Contenido |
|------|---------|
| `/tmp/yu-scan/worker.pid` | PID del trabajador |
| `/tmp/yu-scan/progress.json` | Progreso (JSON: running, phase, current, total, percent, message, detail, error) |

La WebUI sondea este archivo de progreso y retransmite los datos a través de `GET /api/scan/status` y eventos SSE (`scan.progress`, `scan.complete`).

## Errores de Escaneo

### GET /api/scan-errors

Lista de errores que ocurrieron durante el escaneo.

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `type` | string | Filtro de tipo de error |
| `resolved` | bool | Solo errores resueltos |
| `limit` | int | Número de resultados |

### POST /api/scan-errors/<id>/resolve

Marcar un error como resuelto.

### POST /api/scan-errors/clear

Eliminar todos los errores resueltos de una vez.

## Gestión de Raíz de Escaneo

### GET /api/scan-roots

Listar raíces de escaneo registradas.

### Respuesta

```json
{
  "roots": [
    {
      "path": "O:\\webui\\outputs",
      "enabled": true,
      "file_count": 15000
    }
  ]
}
```

### POST /api/scan-roots

Agregar una raíz de escaneo.

```json
{
  "path": "O:\\webui\\outputs"
}
```

### PUT /api/scan-roots/<index>

Actualizar una raíz de escaneo (cambiar ruta, alternar habilitado/deshabilitado).

### DELETE /api/scan-roots/<index>

Eliminar una raíz de escaneo.

## Relleno de Hash

### POST /api/hash-backfill/start

Iniciar cálculo de hash en background para archivos existentes.

### GET /api/hash-backfill/status

Recuperar progreso.

### POST /api/hash-backfill/cancel

Cancelar el cálculo.

## Trabajos en Background

### GET /api/jobs/status

Estado de todos los trabajos en background. Utilizado para visualización de bandera de interfaz de usuario.

```json
{
  "jobs": [
    {
      "type": "scan",
      "status": "running",
      "progress": 45,
      "total": 1500
    }
  ]
}
```
