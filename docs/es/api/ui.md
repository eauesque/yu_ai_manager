# API de Gestión de UI

APIs para listar, cambiar, instalar y desinstalar temas de UI.

## GET /api/ui/list

Listar todas las UIs instaladas. Devuelve información de manifiesto, estado activo y si existen archivos de plantilla/estática para cada UI.

### Parámetros

Ninguno

### Respuesta

```json
{
  "data": {
    "uis": [
      {
        "name": "default",
        "active": true,
        "manifest": {
          "name": "Default UI",
          "version": "1.0.0",
          "description": "Built-in reference UI"
        },
        "has_templates": true,
        "has_static": true
      },
      {
        "name": "custom-dark",
        "active": false,
        "manifest": {
          "name": "Custom Dark",
          "version": "0.2.0",
          "description": "Dark theme variant"
        },
        "has_templates": true,
        "has_static": true
      }
    ]
  }
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `name` | string | Nombre del directorio de UI |
| `active` | boolean | Si esta es la UI actualmente activa |
| `manifest` | object | Contenidos de `manifest.json` |
| `has_templates` | boolean | Si existe un directorio `templates/` |
| `has_static` | boolean | Si existe un directorio `static/` |

## POST /api/ui/switch

Cambiar la UI activa. El cambio se guarda en `config.json` y requiere un reinicio del servidor para entrar en vigor.

### Limitación de Velocidad

WRITE

### Solicitud

```json
{
  "name": "custom-dark"
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `name` | string | Sí | Nombre de UI objetivo. Solo se permiten caracteres alfanuméricos, guiones e guiones bajos |

### Respuesta

```json
{
  "name": "custom-dark",
  "restart_required": true
}
```

### Errores

| Estado | Condición |
|--------|-----------|
| 400 | El nombre de UI está vacío o contiene caracteres inválidos |
| 404 | La UI especificada no existe |
| 400 | `manifest.json` está faltando o no es válido |
| 500 | Falló guardar `config.json` |

## POST /api/ui/install

Instalar una UI desde una URL. **Solo se permite desde localhost.**

### Limitación de Velocidad

WRITE

### Autenticación

Requiere autenticación PIN o Clave API, más la solicitud debe originarse desde localhost. Las solicitudes remotas se rechazan con 403.

### Solicitud

```json
{
  "url": "https://github.com/user/my-ui/archive/refs/heads/main.zip"
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `url` | string | Sí | URL del paquete de UI (archivo zip, etc.) |

### Respuesta

```json
{
  "name": "my-ui",
  "installed": true
}
```

### Errores

| Estado | Condición |
|--------|-----------|
| 400 | La URL está vacía |
| 403 | La solicitud no es desde localhost |

## DELETE /api/ui/<name>/uninstall

Desinstalar una UI. **Solo se permite desde localhost.** La UI predeterminada (`default`) no se puede eliminar.

Si la UI desinstalada está actualmente activa, la configuración de UI en `config.json` se restablece y se restaura la UI predeterminada.

### Limitación de Velocidad

WRITE

### Autenticación

Requiere autenticación PIN o Clave API, más la solicitud debe originarse desde localhost. Las solicitudes remotas se rechazan con 403.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `name` | string | Nombre de UI (parámetro de ruta). Solo caracteres alfanuméricos, guiones e guiones bajos |

### Respuesta

```json
{
  "name": "custom-dark",
  "uninstalled": true
}
```

### Errores

| Estado | Condición |
|--------|-----------|
| 400 | Nombre de UI inválido, o intento de desinstalar `default` |
| 403 | La solicitud no es desde localhost |
| 404 | La UI especificada no existe |
