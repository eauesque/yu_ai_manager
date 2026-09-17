# Registro de Archivos Arrastra y Suelta

Arrastra y suelta archivos de imagen/video en la página de biblioteca principal (`/`) para guardarlos
en un directorio **Drop Inbox** configurado y registrarlos automáticamente en
la biblioteca. Se utiliza la ruta de escaneo normal (`scan_one`), por lo que la extracción de metadatos,
generación de miniaturas y etiquetado se ejecutan como lo harían para un escaneo normal.

## Comportamiento

1. Con la página principal abierta, arrastra archivos desde el explorador de archivos u otro navegador
2. Aparece una superposición en la ventana mostrando el destino (directorio Drop Inbox)
3. Al soltar, cada archivo se copia en el Drop Inbox y se registra
4. Un toast muestra el número de éxitos y fallos

## Resolución de Drop Inbox

El Drop Inbox se resuelve en esta prioridad:

1. `drop_inbox_dir` de `config.json` (configuración explícita)
2. Si no está configurado: la primera raíz de escaneo habilitada se utiliza tal cual

**Restricción**: `drop_inbox_dir` **debe** residir dentro de una de las entradas
`scan_roots`. Cualquier ruta fuera de las raíces de escaneo se rechaza con HTTP 400. Esto preserva
la invariante de que las raíces de escaneo son la única fuente de verdad para los archivos de la biblioteca.

## Ejemplo de Configuración

```json
{
  "scan_roots": [
    { "path": "D:/Pictures/AI", "enabled": true, "recursive": true }
  ],
  "drop_inbox_dir": "D:/Pictures/AI/inbox"
}
```

El `drop_inbox_dir` se crea si no existe (su directorio padre todavía debe estar
dentro de `scan_roots`).

## Manejo de Colisión de Nombres

Si un archivo con el mismo nombre ya existe en la bandeja de entrada, los sufijos `_1`, `_2`,
... se añaden automáticamente. Los archivos existentes nunca se sobrescriben.

## Extensiones Permitidas

| Categoría | Extensiones |
|---|---|
| Imágenes | `.png` `.jpg` `.jpeg` `.webp` `.gif` `.bmp` `.tiff` `.tif` `.svg` |
| Videos | `.mp4` `.webm` `.mov` `.avi` `.mkv` `.m4v` |

Los archivos (`.zip` / `.7z` / `.rar`) **no se admiten** vía arrastra y suelta. Coloca
los archivos de archivo directamente en una raíz de escaneo y ejecuta un escaneo regular en su lugar.

## Limitaciones

- El tamaño total de la solicitud tiene un límite de `MAX_CONTENT_LENGTH` (predeterminado **100 MB**)
- Los nombres de archivo que contienen travesía de ruta (`..`) se rechazan
- Soltar un directorio completo actualmente no se admite (solo archivos individuales)

## API HTTP

### `POST /api/dnd-upload`

Acepta cargas de archivos multiparte, las guarda en el Drop Inbox y las registra
en la biblioteca.

Respuesta:

```json
{
  "ok": true,
  "total": 3,
  "success": 2,
  "results": [
    { "ok": true, "status": "added", "file_id": 12345, "path": "...", "filename": "a.png" },
    { "ok": true, "status": "skipped", "path": "...", "filename": "b.png" },
    { "ok": false, "code": "unsupported_type", "error": "...", "filename": "c.xyz" }
  ]
}
```

### `GET /api/dnd-inbox`

Devuelve el Drop Inbox actualmente resuelto para que la superposición de UI muestre.

```json
{ "ok": true, "inbox": "D:/Pictures/AI/inbox", "explicit": true }
```

### `POST /api/files/register-path`

Registra un archivo que ya está en disco por ruta (sin carga). La ruta debe estar dentro
de `scan_roots`. Utilizado por la herramienta MCP `register_file`.

```json
{ "path": "D:/Pictures/AI/inbox/a.png" }
```

## Herramientas MCP

| Herramienta | Descripción |
|---|---|
| `register_file(path)` | Registrar un archivo en una ruta absoluta en la biblioteca |
| `drop_inbox_info()` | Devolver el directorio Drop Inbox actualmente resuelto |
