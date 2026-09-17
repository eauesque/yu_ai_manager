# Especificación de Acceso LAN MCP y Endpoint de Ayuda

**Versión de implementación**: 3.1.0
**Documentación relacionada**: `docs/en/features/mcp-integration-guide.md`
**Archivos relacionados**: `routes/mcp_endpoint.py`, `routes/help.py`, `mcp_server/help_tools.py`

---

## Descripción General

1. **Acceso LAN MCP** — Permitir que clientes MCP en la LAN se conecten al endpoint MCP por dirección IP cuando el modo de compartir LAN está habilitado
2. **Endpoint `/help`** — Proporcionar un manual web integrado para la aplicación (también publicado como recurso MCP)

---

## 1. Acceso LAN MCP

### 1-1. Arquitectura

En la LAN, los clientes MCP se conectan directamente al endpoint `/mcp` de YU AI Manager usando transporte HTTP/SSE.

### 1-2. Endpoint MCP SSE

| Elemento | Detalles |
|------|------|
| Endpoint | `/mcp` (SSE + publicación de mensajes) |
| Transporte | HTTP + Eventos Enviados por Servidor (SSE) |
| Autenticación | No requerida desde localhost. Se requiere clave de API desde IPs de LAN |

### 1-3. Autenticación por Clave de API

Se reutiliza el mecanismo de gestión de clave de API existente (`/api/keys`).

### 1-4. UI de Configuración

Se añade un fragmento de configuración de conexión LAN MCP (versión HTTP) a la pestaña Configuración > Claves de API.

---

## 2. Endpoint `/help`

### 2-1. Principios de Diseño

- Completamente sin conexión
- Propósito dual como recurso MCP
- No se requiere autenticación

### 2-2. Endpoints

| Endpoint | Contenido |
|----------------|------|
| `GET /help` | Página superior del manual |
| `GET /help/<section>` | Página específica de sección |
| `GET /api/help/toc` | JSON de tabla de contenidos |
| `GET /api/help/content/<section>` | JSON del cuerpo de sección |

### 2-3. Herramientas MCP

- `help_search`: Búsqueda por palabra clave
- `help_get_section`: Recuperación de sección
