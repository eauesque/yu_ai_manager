# Integración MCP

YU AI Manager tiene un servidor MCP (Model Context Protocol) integrado que puede operarse directamente desde clientes de IA como Claude Desktop, Claude Code y Cline.
Proporciona más de 137 herramientas con acceso a todas las funciones, desde la gestión de imágenes hasta el análisis de IA.

## Clientes MCP compatibles

| Cliente | Método de conexión | Notas |
|-------------|---------|------|
| Claude Desktop | stdio / HTTP | Cliente recomendado |
| Claude Code | stdio | Entorno CLI |
| Cline (VS Code) | stdio | Extensión de VS Code |
| Open WebUI | HTTP/SSE | Basado en web |

## Conexión local (stdio)

Al conectar desde Claude Desktop / Claude Code en la misma máquina:

1. Crear una clave API en la pestaña Settings > API Keys
2. Agregar lo siguiente al archivo de configuración del cliente

### Claude Desktop

`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://localhost:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

### Claude Code

`.mcp.json`:

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://localhost:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

## Conexión LAN (HTTP/SSE)

Al conectar desde otra máquina en la LAN:

1. Activar LAN Access en YU AI Manager
2. Crear una clave API
3. Copiar la configuración de conexión desde "MCP Connection Snippet" en la pestaña Settings > API Keys

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "type": "http",
      "url": "http://192.168.x.x:5000/mcp",
      "headers": {
        "Authorization": "Bearer sk_your_api_key_here"
      }
    }
  }
}
```

## Herramientas disponibles (por categoría)

### Búsqueda y gestión de imágenes

| Herramienta | Descripción |
|--------|------|
| `search_images` | Búsqueda filtrada por etiquetas, fecha, puntuación, etc. |
| `get_image_detail` | Obtener metadatos detallados de imagen |
| `get_library_stats` | Estadísticas de la biblioteca (número de archivos, distribución de etiquetas, etc.) |
| `find_similar` | Detección de imágenes similares por hash perceptual |
| `rate_images` | Establecer puntuación por estrellas en lote |
| `set_tags` | Agregar/eliminar etiquetas |
| `set_annotations` | Establecer anotaciones |
| `get_annotations` | Obtener anotaciones |

### Colecciones

| Herramienta | Descripción |
|--------|------|
| `list_collections` | Lista de colecciones |
| `create_collection` | Crear colección |
| `add_to_collection` | Agregar imagen a colección |
| `remove_from_collection` | Eliminar imagen de colección |
| `delete_collection` | Eliminar colección |

### Escaneo

| Herramienta | Descripción |
|--------|------|
| `trigger_scan` | Ejecutar escaneo |
| `get_scan_status` | Verificar progreso del escaneo |
| `list_scan_roots` | Lista de raíces de escaneo |
| `add_scan_root` | Agregar raíz de escaneo |
| `scan_directory` | Escanear directorio específico |

### Análisis de IA

| Herramienta | Descripción |
|--------|------|
| `analyze_image` | Análisis de imagen con IA (individual) |
| `analyze_batch` | Análisis de imagen con IA (en lote) |
| `wd_tagger_tag_file` | Inferencia WD-Tagger (individual) |
| `wd_tagger_batch` | Inferencia WD-Tagger (en lote) |
| `semantic_search` | Búsqueda semántica CLIP |
| `s2t_transcribe_video` | Transcripción de voz |

### Integración Bridge

| Herramienta | Descripción |
|--------|------|
| `sd_generate` | Generación de imágenes con SD WebUI |
| `sd_list_models` | Lista de modelos de SD WebUI |
| `comfyui_generate` | Generación de imágenes con ComfyUI |
| `comfyui_generate_json` | Ejecutar flujo de trabajo JSON de ComfyUI |

### Biblioteca de prompts

| Herramienta | Descripción |
|--------|------|
| `create_prompt` | Crear prompt |
| `search_prompts` | Buscar prompts |
| `get_prompt` | Obtener prompt |
| `update_prompt` | Actualizar prompt |

### Configuración

| Herramienta | Descripción |
|--------|------|
| `settings_get_schema` | Obtener esquema de configuración |
| `settings_get` | Obtener valor de configuración |
| `settings_set` | Actualizar valor de configuración |
| `secrets_status` | Verificar estado de clave de cifrado |

### Mecanismo de seguridad para agentes

| Herramienta | Descripción |
|--------|------|
| `agent_kill` / `agent_resume` | Control del Kill Switch |
| `agent_status` | Estado del mecanismo de seguridad |
| `agent_journal` | Buscar en el diario de operaciones |
| `agent_undo` | Deshacer operación |
| `agent_circuit_breaker_status` | Estado del Circuit Breaker |
| `agent_budget_status` | Estado del rastreador de presupuesto |
| `agent_scope_set` | Configurar scope |
| `agent_anomaly_status` | Estado de detección de anomalías |

### Otros

| Herramienta | Descripción |
|--------|------|
| `find_duplicates` | Detección de archivos duplicados |
| `search_chat_logs` | Búsqueda en registros de chat |
| `search_md_files` | Búsqueda de archivos Markdown |
| `help_search` | Búsqueda en documentación de ayuda |
| `share_to_bluesky` | Publicar en Bluesky |
| `list_trophies` | Lista de trofeos |
| `get_monthly_report` | Informe mensual |

## Variables de entorno

| Variable | Descripción | Predeterminado |
|------|------|----------|
| `YU_BASE_URL` | URL del servidor | `http://localhost:5000` |
| `YU_API_KEY` | Clave API | (obligatorio) |
| `YU_DEBUG_MODE` | Habilitar herramientas de depuración | `0` |

Con `YU_DEBUG_MODE=1` se agregan herramientas de depuración dedicadas como consulta directa a BD y verificación de salud.

## Solución de problemas

### No se puede conectar

1. Verificar que YU AI Manager está en ejecución
2. Verificar que la clave API es correcta (con prefijo `sk_`)
3. Verificar que `YU_BASE_URL` es correcto
4. En caso de conexión LAN, verificar que LAN Access está activado

### Herramienta no encontrada

- Si una extensión está deshabilitada, sus herramientas también quedan no disponibles
- Verificar el estado de habilitación con `list_extensions`

### Timeout

- Las búsquedas en bibliotecas de gran escala y las operaciones en lote pueden tomar tiempo
- Limitar el número de resultados con el parámetro `limit`
