# Guía de Integración MCP — Operar YU AI Manager desde un LLM

YU AI Manager tiene un servidor **MCP (Model Context Protocol)** integrado que permite que aplicaciones LLM operen la biblioteca de imágenes usando lenguaje natural.

No hay UI de chat integrada en esta aplicación.
Para interactuar con ella usando lenguaje natural, conéctate desde tu cliente compatible con MCP preferido.

---

## ¿Qué es MCP?

MCP (Model Context Protocol) es un protocolo estándar que permite que aplicaciones LLM accedan a herramientas externas y fuentes de datos.
YU AI Manager actúa como servidor MCP, y clientes LLM (como Claude Desktop) se conectan a él, traduciendo instrucciones en lenguaje natural en operaciones de API.

```
┌─────────────────┐      MCP (stdio)       ┌─────────────────────┐
│  Cliente LLM    │ <--------------------> │  YU AI Manager      │
│  (Claude Desktop│                        │  Servidor MCP       │
│   / Open WebUI  │                        │  (python -m         │
│   / Cline etc.) │                        │   mcp_server)       │
└─────────────────┘                        └────────┬────────────┘
                                                     │ API HTTP
                                                     v
                                           ┌─────────────────────┐
                                           │  YU AI Manager      │
                                           │  Servidor Web       │
                                           │  (localhost:5000)   │
                                           └─────────────────────┘
```

## Clientes MCP Soportados

Los siguientes son clientes representativos compatibles con MCP. Los pasos de configuración son similares para todos.

| Cliente | Proveedor | Características |
|---|---|---|
| **Claude Desktop** | Anthropic | Acceso directo a Claude. Soporte MCP nativo |
| **Claude Code** | Anthropic | Cliente basado en terminal para desarrolladores |
| **Cline** | Extensión VS Code | Integración del editor. Soporte multi-LLM |
| **Open WebUI** | Código Abierto | Auto-alojado. Puede combinarse con LLM locales como Ollama |

Nota: El número de clientes compatibles con MCP está creciendo rápidamente.
Cualquier cliente que soporta transporte stdio debería poder conectarse.

## Configuración

### 1. Iniciar YU AI Manager

El servidor MCP opera a través de la API del servidor Web, por lo que YU AI Manager debe estar ejecutándose primero.

```bash
python web_ui.py --db ./tags.db --port 5000
```

### 2. Emitir una Clave de API (Recomendado)

Emitir una clave de API permite que el servidor MCP evite autenticación PIN cuando se usa compartir LAN o autenticación PIN.

Las claves de API se pueden emitir desde Configuración -> Claves de API.

Una clave de API no es necesaria cuando se ejecuta sin PIN (`config_test.json`).

### 3. Añadir Configuración de Conexión a Tu Cliente MCP

#### Claude Desktop

Editar `claude_desktop_config.json`:

**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "C:/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://127.0.0.1:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

#### Claude Code

Añadir configuración a `.mcp.json` en la raíz del proyecto, o usar el comando `claude mcp add`:

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://127.0.0.1:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

#### Cline (VS Code)

Introducir la misma información a través de la Configuración MCP de Cline.

#### Variables de Entorno

| Variable | Requerida | Predeterminado | Descripción |
|---|---|---|---|
| `YU_BASE_URL` | - | `http://localhost:5000` | URL del servidor web |
| `YU_API_KEY` | - | Ninguno | Clave de API (requerida en entornos PIN) |
| `YU_DEBUG_MODE` | - | `0` | Establecer a `1` para añadir herramientas de depuración |

## Ejemplos de Uso

Una vez conectado, puedes operar la biblioteca de imágenes dando instrucciones en lenguaje natural al LLM.

### Búsqueda y Navegación

```
"Muéstrame las 20 imágenes más recientes de chicas con ojos azules"
"Filtrar solo imágenes generadas con NovelAI"
"Muéstrame estadísticas para imágenes escaneadas la semana pasada"
```

### Organizar y Clasificar

```
"Dar a estas 10 imágenes una calificación de 5 estrellas"
"Añadir imágenes etiquetadas 'landscape' a la 'Colección Scenery'"
"Listar todas las imágenes con una calificación de 3 o inferior"
```

### Análisis y Anotación

```
"Puntuar la calidad de imágenes recientemente añadidas y guardar a anotaciones"
"Muéstrame todas las anotaciones para la imagen ID 12345"
"Buscar anotaciones con fuente agent:claude"
```

### Operaciones de Escaneo

```
"Escanear nuevas imágenes"
"Verificar el progreso del escaneo"
"Muéstrame cualquier error de escaneo"
```

## Herramientas Disponibles

El servidor MCP expone las siguientes herramientas al LLM:

### Búsqueda y Navegación (4 herramientas)

| Nombre de Herramienta | Descripción |
|---|---|
| `search_images` | Buscar imágenes por etiquetas, fecha, formato, calificación, etc. |
| `get_image_detail` | Recuperar todos los metadatos para una imagen |
| `get_library_stats` | Estadísticas de biblioteca (recuento de archivos, recuento de etiquetas, distribución de fuentes, etc.) |
| `find_similar` | Buscar imágenes similares usando hash perceptual |

### Colecciones (4 herramientas)

| Nombre de Herramienta | Descripción |
|---|---|
| `list_collections` | Listar colecciones |
| `create_collection` | Crear una colección |
| `delete_collection` | Eliminar una colección |
| `add_to_collection` / `remove_from_collection` | Añadir/eliminar imágenes |

### Etiquetas y Calificaciones (2 herramientas)

| Nombre de Herramienta | Descripción |
|---|---|
| `rate_images` | Establecer calificaciones de estrellas para múltiples imágenes a la vez |
| `set_tags` | Añadir/eliminar etiquetas para múltiples imágenes a la vez |

### Anotaciones (4 herramientas)

| Nombre de Herramienta | Descripción |
|---|---|
| `set_annotations` | Guardar resultados de análisis de IA como anotaciones |
| `get_annotations` | Recuperar anotaciones para una imagen |
| `search_annotations` | Buscar anotaciones en fuente, clave y confianza |
| `delete_annotations` | Eliminar anotaciones |

### Escaneo (3 herramientas)

| Nombre de Herramienta | Descripción |
|---|---|
| `trigger_scan` | Iniciar un escaneo |
| `get_scan_status` | Verificar progreso del escaneo |
| `get_scan_errors` | Listar errores de escaneo |

### Otro

También se incluyen herramientas para biblioteca de prompts, copia de seguridad y gestión de cliente MCP.

## FAQ

### P: ¿No hay función de chat en la aplicación?

R: No la hay. YU AI Manager se especializa en gestión de metadatos de imágenes, y la interfaz de IA conversacional se delega a clientes compatibles con MCP. Puedes realizar todas las operaciones vía lenguaje natural ejecutando Claude Desktop o un cliente similar junto a él.

### P: ¿Qué LLM debo usar?

R: Cualquier LLM funciona, siempre que el cliente MCP lo soporta.
Para manejo confiable de argumentos de herramientas, los modelos a gran escala como Claude o GPT-4 tienden a funcionar más consistentemente.

### P: ¿Puedo usar un LLM local?

R: Sí, los LLM locales funcionan con combinaciones como Open WebUI + Ollama, siempre que soporten MCP. Sin embargo, la precisión del llamado de herramientas depende de las capacidades del modelo.

### P: ¿YU AI Manager también tiene una función de cliente MCP?

R: La extensión `MCP Client` (en la página de Herramientas) conecta YU AI Manager a **otros servidores MCP**. Esta guía describe la dirección opuesta: LLM externo -> YU AI Manager.
