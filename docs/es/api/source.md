# API de Navegación de Código Fuente

Una API de solo lectura para navegar el código fuente del proyecto.
Está diseñada para que las herramientas MCP y los agentes de IA externos puedan ver y buscar de forma segura el código base.

## Modelo de Seguridad

Tres capas de defensa garantizan la seguridad:

### 1. Normalización de Ruta (Prevención de Traversal)

- Todas las rutas se normalizan con `os.path.realpath()` y se verifican contra la raíz del proyecto a través de coincidencia de prefijo.
- Los ataques de traversal como `../../etc/passwd` o `../../../Windows/System32` se bloquean.
- La inyección de byte nulo (`\x00`) también se detecta y rechaza.

### 2. Lista Blanca de Extensión

Extensiones de archivo permitidas para lectura:

| Categoría | Extensiones |
|----------|-----------|
| Python | `.py` |
| TypeScript / JavaScript | `.ts`, `.js`, `.mjs`, `.tsx`, `.jsx` |
| Web | `.html`, `.css`, `.scss` |
| Configuración | `.json`, `.yaml`, `.yml`, `.toml`, `.cfg`, `.ini` |
| Documentación | `.md`, `.txt`, `.rst` |
| Scripts | `.sh`, `.bat`, `.cmd`, `.ps1` |
| Otros | `.sql`, `.gitignore`, `.gitattributes`, `.editorconfig` |

Los siguientes archivos sin extensión están especialmente permitidos: `Dockerfile`, `Makefile`, `Procfile`, `VERSION`, `LICENSE`, `CHANGELOG`, `TODO`

### 3. Lista Negra de Archivo Sensible

Los archivos que coinciden con los siguientes patrones se rechazan:

| Patrón | Motivo |
|---------|--------|
| `config.json`, `config_*.json` | Datos de autenticación como PIN y Clave API |
| `*.env`, `.env.*` | Variables de entorno (secretos) |
| `secret.salt`, `*.key`, `*.pem`, `*.cert` | Claves de cifrado y certificados |
| `credentials*`, `*token*`, `*secret*` | Datos de autenticación |
| `*.db`, `*.sqlite*` | Archivos de base de datos |
| `pnpm-lock.yaml`, `package-lock.json`, etc. | Archivos de bloqueo (grandes) |
| Archivos de imagen, video, fuente y modelo | Archivos binarios |

### Directorios Bloqueados

`.git`, `__pycache__`, `node_modules`, `venv`, `dist`, `data`, `backups`, `screenshots`, `reports`, `src-tauri`

### Límites de Lectura

| Artículo | Límite |
|------|-------|
| Tamaño de archivo | 1 MB |
| Líneas por lectura | 2,000 |
| Profundidad de traversal de árbol | 6 |
| Resultados de búsqueda | 50 |

---

## Endpoints

### GET /api/source/tree

Recuperar un árbol de directorio.

#### Parámetros

| Parámetro | Tipo | Predeterminado | Descripción |
|-----------|------|---------|-------------|
| `path` | string | `""` (raíz) | Ruta relativa |
| `depth` | int | `3` | Profundidad de traversal (1-6) |

#### Respuesta

```json
{
  "ok": true,
  "root": ".",
  "depth": 3,
  "entries": [
    {
      "name": "core",
      "type": "dir",
      "path": "core",
      "children": [
        {
          "name": "source_core",
          "type": "dir",
          "path": "core/source_core",
          "children": [
            {
              "name": "source_browser.py",
              "type": "file",
              "path": "core/source_core/source_browser.py",
              "size": 8234
            }
          ]
        }
      ]
    },
    {
      "name": "web_ui.py",
      "type": "file",
      "path": "web_ui.py",
      "size": 3456
    }
  ]
}
```

- Los directorios aparecen primero, seguidos de archivos (ordenados por nombre).
- `size` está en bytes (solo archivos).
- `children` se omite una vez que el traversal alcanza la profundidad especificada.

---

### GET /api/source/read

Leer contenido de archivo con números de línea.

#### Parámetros

| Parámetro | Tipo | Predeterminado | Descripción |
|-----------|------|---------|-------------|
| `path` | string | — (requerido) | Ruta de archivo relativa |
| `offset` | int | `0` | Línea inicial (basada en 0) |
| `limit` | int | `2000` | Número máximo de líneas |

#### Respuesta

```json
{
  "ok": true,
  "path": "core/source_core/source_browser.py",
  "total_lines": 250,
  "offset": 0,
  "limit": 2000,
  "content": "    1\t\"\"\"Source code browser...\n    2\t\n    3\timport os\n..."
}
```

- `content` usa formato `{line_number}\t{line_content}`.
- Use `offset` + `limit` para paginar a través de archivos largos.

#### Ejemplos de Error

```json
{
  "ok": false,
  "error": "This file is not eligible for reading"
}
```

```json
{
  "ok": false,
  "error": "Access outside the project root is prohibited"
}
```

---

### GET /api/source/search

Buscar dentro del código fuente por texto.

#### Parámetros

| Parámetro | Tipo | Predeterminado | Descripción |
|-----------|------|---------|-------------|
| `q` | string | — (requerido) | Texto de búsqueda (mínimo 2 caracteres) |
| `glob` | string | `""` (todos los archivos) | Filtro de nombre de archivo (p. ej., `*.py`) |
| `limit` | int | `30` | Número máximo de resultados (1-50) |

#### Respuesta

```json
{
  "ok": true,
  "query": "def source_tree",
  "glob": "*.py",
  "total": 2,
  "results": [
    {
      "file": "core/source_core/source_browser.py",
      "line": 120,
      "text": "def source_tree("
    },
    {
      "file": "routes/source_api.py",
      "line": 15,
      "text": "    result = source_tree(rel_path, depth_int)"
    }
  ]
}
```

- La búsqueda no distingue entre mayúsculas y minúsculas.
- `text` se trunca a un máximo de 200 caracteres.

---

## Herramientas MCP

| Herramienta | Descripción | Parámetros Clave |
|------|-------------|----------------|
| `source_tree` | Mostrar árbol de directorio | `path`: str = '', `depth`: int = 3 |
| `source_read` | Leer contenido de archivo | `path`: str (requerido), `offset`: int = 0, `limit`: int = 2000 |
| `source_search` | Buscar código fuente por texto | `query`: str (requerido), `glob`: str = '', `limit`: int = 30 |

### Ejemplos de Uso con MCP

```
# Ver la estructura del proyecto
source_tree(path="", depth=2)

# Leer un archivo específico
source_read(path="core/source_core/source_browser.py")

# Buscar dentro del código base
source_search(query="def register_blueprints", glob="*.py")
```

### Alcance y Limitación de Velocidad

- **Fence de Alcance**: Disponible en alcance `read_only` (permitido en todos los presets)
- **Seguimiento de Presupuesto**: Categoría `read` (sin límite de velocidad)
- **Gate HITL**: Nivel 0 (sin aprobación requerida)

---

## Archivos de Implementación

| Archivo | Rol |
|------|------|
| `core/source_core/source_browser.py` | Capa de seguridad + lógica de negocio |
| `routes/source_api.py` | Endpoints de API Flask (Blueprint) |
| `mcp_server/source_tools.py` | Registro de herramientas MCP |
