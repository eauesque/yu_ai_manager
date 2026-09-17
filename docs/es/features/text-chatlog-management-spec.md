# Especificación de Gestión de Texto y Chatlog de YU AI Manager

Creado: 2026-03-01
Versión objetivo: TBD (momento de implementación bajo consideración)

## Descripción General

Se añaden tres características a YU AI Manager:

- **MD Viewer** — Visualización local de archivos Markdown
- **Gestión de Chatlog** — Importar, ver y buscar registros de Claude/ChatGPT/Open WebUI
- **Búsqueda de Texto Completo** — Búsqueda entre contenido impulsada por FTS5

La filosofía de diseño es la misma que las características existentes: "completamente local, sin dependencia de nube."

---

## 1. MD Viewer

### Propósito

Los visualizadores de archivos del SO proporcionan pobre renderizado de Markdown. Esta característica aporta visualización de Markdown completamente dentro de YU AI Manager, sirviendo como herramienta de referencia diaria para notas de desarrollo, documentos de diseño y listas TODO.

### Destinos de Escaneo

- Extensiones: `.md`, `.markdown`
- Se reutilizan las raíces de escaneo existentes
- Excluido: archivos bajo `.git/` y `node_modules/`

### Esquema de BD

```sql
CREATE TABLE md_files (
    id          INTEGER PRIMARY KEY,
    path        TEXT NOT NULL UNIQUE,
    mtime       INTEGER NOT NULL,
    size        INTEGER NOT NULL,
    title       TEXT,        -- Extraído del encabezado # primero
    content     TEXT,        -- Texto Markdown sin formato
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    indexed_at  INTEGER
);

CREATE VIRTUAL TABLE md_files_fts USING fts5(
    title,
    content,
    content='md_files',
    content_rowid='id'
);
```

### UI del Visualizador

- Integrado en el modal existente o panel lateral
- Renderizado: marked.js (agrupado localmente, sin CDN)
- Bloques de código: resaltado de sintaxis (highlight.js)
- Se proporciona botón de alternancia de visualización de texto sin formato

### Soporte MCP

- `search_md_files(query, path_filter)` -> lista de archivos
- `get_md_content(file_id)` -> texto sin formato

---

## 2. Gestión de Chatlog

### Propósito

Esta característica sirve como motor de búsqueda para historial de desarrollo, haciendo posible encontrar discusiones pasadas usando palabras clave vagas. Ejemplos: "¿Dónde estaba esa discusión de bug?" o "¿Cuál era la razón de esa decisión de diseño?"

### Formatos Soportados

| Servicio | Formato de Exportación | Cómo Obtener |
|---|---|---|
| Claude | conversations.json | Configuración -> Exportar Datos |
| ChatGPT | conversations.json | Configuración -> Exportar Datos |
| Open WebUI | Exportación JSON | Historial de Chat -> Exportar |

### Esquema de BD

```sql
-- Por conversación
CREATE TABLE chat_conversations (
    id            INTEGER PRIMARY KEY,
    source        TEXT NOT NULL,  -- 'claude' / 'chatgpt' / 'openwebui'
    external_id   TEXT,           -- ID de conversación del servicio original
    title         TEXT,
    model         TEXT,           -- Nombre del modelo utilizado
    created_at    INTEGER,
    updated_at    INTEGER,
    message_count INTEGER,
    imported_at   INTEGER NOT NULL
);

-- Por mensaje
CREATE TABLE chat_messages (
    id              INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id),
    role            TEXT NOT NULL,  -- 'user' / 'assistant' / 'system'
    content         TEXT NOT NULL,
    created_at      INTEGER,
    seq             INTEGER         -- Orden dentro de la conversación
);

-- Búsqueda de texto completo FTS5
CREATE VIRTUAL TABLE chat_messages_fts USING fts5(
    content,
    content='chat_messages',
    content_rowid='id',
    tokenize='unicode61'
);
```

### Importador

El JSON de cada servicio se convierte a un formato intermedio común e se inserta en BD.

**Estructura JSON de Claude (campos clave):**

```json
{
  "uuid": "...",
  "name": "Título de conversación",
  "created_at": "2026-01-01T00:00:00Z",
  "chat_messages": [
    {"role": "human", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

**Estructura JSON de ChatGPT (campos clave):**

```json
{
  "id": "...",
  "title": "Título de conversación",
  "create_time": 1234567890,
  "mapping": {
    "node_id": {
      "message": {
        "author": {"role": "user"},
        "content": {"parts": ["..."]}
      }
    }
  }
}
```

**Estructura JSON de Open WebUI:**

- Sigue el formato de API compatible con OpenAI
- array de mensajes con role/content

### UI de Importación

- Se añade una sección de importación a la página de configuración
- Los archivos JSON se pueden soltar vía arrastra y suelta o seleccionar con un selector de archivo
- Las conversaciones previamente importadas se deduplicar por `external_id` (idempotente)
- Se muestra un resumen de importación (recuento añadido y recuento omitido)

### UI del Visualizador

- Página de lista de conversaciones (título, fecha, modelo, fuente)
- Página de detalle de conversación (visualización basada en turnos con codificación de color basada en rol)
- Filtros por nombre de modelo, fuente y rango de fechas
- Las imágenes adjuntas almacenan solo referencias de ruta (sin copias de archivo)

### Soporte MCP

- `search_chat_logs(query, source, model, date_from, date_to)` -> lista de conversaciones
- `get_conversation(conversation_id)` -> lista de mensajes
- `import_chat_log(source, json_path)` -> ejecutar importación

---

## 3. Búsqueda de Texto Completo

### Destinos

- Archivos MD (`md_files_fts`)
- Registros de chat (`chat_messages_fts`)
- Biblioteca de prompts existente (`prompt_library_fts`, ya implementada)

### UI de Búsqueda

- Extender la barra de búsqueda existente o proporcionar una página de búsqueda de texto dedicada
- Alternar destinos de búsqueda (MD / chatlog / biblioteca de prompts)
- Resultados clasificados por puntuación BM25
- Visualización de fragmento de acierto (~50 caracteres de contexto circundante)

### API de Búsqueda

```
GET /api/text-search?q=keyword&target=md,chat,prompt&limit=20
```

Respuesta:

```json
{
  "results": [
    {
      "type": "chat",
      "conversation_id": 123,
      "title": "Título de conversación",
      "snippet": "...texto alrededor del acierto...",
      "score": 0.95,
      "date": "2026-01-01"
    }
  ]
}
```

---

## Prioridad de Implementación

1. MD Viewer (bajo costo de implementación, alto valor inmediato)
2. Importador de chatlog (soporte Claude/ChatGPT primero)
3. Visualizador de chatlog
4. Soporte de Open WebUI
5. UI de búsqueda de contenido cruzado de texto

---

## Extensiones Futuras

- Importación de chatlog periódica automática (colocar archivos de exportación en una carpeta observada para ingestión automática)
- Vincular prompts de generación de imágenes a las discusiones de chatlog que las produjeron
- Resumen automático de chatlog y etiquetado vía Ollama

---

## Notas

- Los patrones FTS5 se pueden reutilizar de la implementación existente `prompt_library_fts`
- marked.js se agrupa localmente en lugar de cargarse desde un CDN (siguiendo la filosofía de solo local)
- Las imágenes adjuntas en chatlogs (imágenes generadas por DALL-E, etc.) no se guardan localmente porque sus URLs expiran
