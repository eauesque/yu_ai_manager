# Gateway — Guía de Límites de Autenticación LAN

> Versión objetivo: Gateway Phase 1 (v4.75.0 en adelante) / Gradio añadido (v4.255.11 en adelante)

## ¿Qué es Gateway?

Gateway es un proxy inverso que protege el acceso a **herramientas backend sin autenticación** como SD WebUI, ComfyUI, Ollama y aplicaciones Gradio mediante **Bearer tokens + modelo de alcances**.

### Diferencia con LLM Router

| | Gateway | LLM Router |
|---|---|---|
| **Objetivo** | SD WebUI, ComfyUI, Ollama, Gradio en conjunto | Solo LLM (Ollama) |
| **Autenticación** | Bearer basado en alcances requerido | loopback puede omitirse |
| **Destino proxy** | `/sd/*`, `/comfy/*`, `/v1/*`, `/gradio/<name>/*` | Solo `/v1/*` |
| **Uso principal** | Exposición segura de herramientas de generación a externos / LAN | Backend para herramientas de codificación de IA |

Ambas pueden estar habilitadas en la misma máquina.

---

## Configuración

### 1. Crear la primera clave API (CLI)

```bash
uv run python -m core.gateway.cli create-key --id admin-local --scopes "*"
```
Ejemplo de salida:
```
id:      admin-local
secret:  gw_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
(este secreto se muestra solo una vez. asegúrese de copiarlo)
```

### 2. Añadir configuración a config.json

> El campo `secret_enc` debe contener el valor encriptado en formato `enc:v2:...` que genera la CLI.
> No escriba el secreto en texto plano directamente en `config.json`.

### 3. Reiniciar la aplicación y confirmar funcionamiento

```bash
GW_HOST=<IP LAN de esta máquina>
GW_PORT=5000
BEARER=<api-key-secret>

# Sin autenticación devuelve 401
curl -i http://$GW_HOST:$GW_PORT/v1/models

# Con Bearer correcto devuelve 200
curl http://$GW_HOST:$GW_PORT/v1/models \
  -H "Authorization: Bearer $BEARER"

# Estado operativo del backend
curl http://$GW_HOST:$GW_PORT/v1/router/capabilities \
  -H "Authorization: Bearer $BEARER"

# Lista de servicios de nodo
curl http://$GW_HOST:$GW_PORT/v1/node/services \
  -H "Authorization: Bearer $BEARER"
```

---

## Interfaz Web (/página gateway)

Panel de administración abierto en `/gateway`.

### Lista de backends

Muestra el estado operativo de los backends registrados.

| Columna | Descripción |
|---|---|
| **Tipo** | Tipo de backend (`ollama`, `sd_webui`, `comfyui`, `gradio`) |
| **Puerto** | Número de puerto del destino proxy |
| **Estado** | `online` / `offline` / `unknown` |
| **Operaciones** | Probe (prueba de conectividad), cambiar configuración |

### Escaneo automático de backends

Al presionar el botón "Escanear", se escanean los puertos comunes locales (7860, 8188, 11434, 7861, etc.) para detectar automáticamente y proponer registro de herramientas en ejecución.

### Gestión de claves API

También es posible añadir y revocar claves API desde la interfaz web (se requiere una clave con alcance `*`).

---

## Lista de Alcances

| Alcance | Puntos finales permitidos |
|---|---|
| `llm:chat` | `POST /v1/chat/completions` |
| `llm:messages` | `POST /v1/messages` (compatible con Anthropic) |
| `llm:models` | `GET /v1/models` |
| `sd:generate` | `POST /sd/sdapi/v1/txt2img`, etc. |
| `sd:query` | `GET /sd/sdapi/v1/samplers`, etc. |
| `sd:admin` | `POST /sd/sdapi/v1/options`, etc. |
| `comfy:generate` | `POST /comfy/api/prompt`, etc. |
| `comfy:query` | `GET /comfy/api/queue`, etc. |
| `memory:read` | `GET /agentmemory/memories`, etc. (lectura) |
| `memory:write` | `POST /agentmemory/observe`, etc. (escritura) |
| `memory:admin` | `POST /agentmemory/migrate`, etc. (administración) |
| `ollama:proxy` | `GET/POST /ollama/<name>/*` (API nativa de Ollama + OpenAI totalmente transparente) |
| `gradio:proxy` | `GET/POST /gradio/<name>/*` (todos los puntos finales transparentes) |
| `gateway:admin` | Gestión de claves API y cambio de configuración (asignado automáticamente desde loopback) |
| `node:status` | `GET /v1/node/services` |
| `*` | Todos los alcances (administrador) |

---

## Proxy de Ollama

Además del `/v1/*` de LLM Router, este proxy transmite de forma transparente la API nativa de Ollama (`/api/*`) y la API compatible con OpenAI (`/v1/*`). Solo cambie el destino de `OLLAMA_HOST` a Gateway para añadir autenticación.

### URL del Proxy

```
/ollama/<backend_name>/<subpath>  →  transmitido a /<subpath> de la base_url registrada
```

### Ejemplo de Configuración

```json
"backends": {
  "ollama": {"type": "ollama", "base_url": "http://127.0.0.1:11434"}
}
```

### Configuración del Cliente (método `OLLAMA_HOST`)

```bash
export OLLAMA_HOST=http://<gateway-host>:5000/ollama/ollama
# todos los comandos ollama siguientes pasarán por Gateway
ollama list
ollama run llama3.3:70b
```

> Si el cliente no puede pasar Bearer a `OLLAMA_HOST`, use `allow_loopback_bypass: true` +
> deje pasar sin clave a través de loopback, o use una clave con alcance `*` como alternativa.

### Transferencia de Archivos de Gran Tamaño

Los blobs del modelo (`/api/blobs/*`) se transmiten sin timeout (otros caminos tienen 300 segundos). La descarga y carga de modelos en escala GB funcionan sin problemas.

---

## Proxy de Gradio

Permite acceso autenticado a través de Gateway para aplicaciones web basadas en Gradio (como Irodori-TTS, etc.). Implementación mínima con transmisión completamente transparente de puntos finales (sin restricción de puntos finales, solo límite de cuerpo de 50 MiB).

### URL del Proxy

```
/gradio/<backend_name>/<subpath>  →  transmitido a /<subpath> de la base_url registrada
```

El nombre del backend (`<backend_name>`) es el nombre de clave registrado en `backends` de `config.json`.

### Ejemplo de Configuración

```json
"backends": {
  "irodori-tts": {"type": "gradio", "base_url": "http://127.0.0.1:7861"}
}
```

### Prueba de Funcionamiento

```bash
GW=http://localhost:5000
KEY=<api-key-secret>

# Obtener información de la aplicación Gradio
curl -H "Authorization: Bearer $KEY" "$GW/gradio/irodori-tts/"

# Predicción compatible con Gradio 3.x
curl -H "Authorization: Bearer $KEY" \
  -X POST "$GW/gradio/irodori-tts/run/predict" \
  -H "Content-Type: application/json" \
  -d '{"data": ["Hello"], "fn_index": 0}'
```

### Limitaciones

- WebSocket (`/queue/join`) no compatible (solo HTTP)
- Flujo SSE de Gradio 4.x (`GET /call/{api_name}/{event_id}`) se transmite con buffer completo, por lo que generaciones prolongadas (video, etc.) pueden agotar el tiempo de espera

---

## Proxy de Agent Memory (agentmemory)

Gateway también proporciona un proxy para que clientes de agentmemory como `@agentmemory/mcp` utilicen de forma segura a través de LAN.

### Puntos Finales

```
/agentmemory/livez       → sin autenticación (comprobación de salud)
/agentmemory/health      → se requiere alcance memory:read
/agentmemory/memories    → memory:read
/agentmemory/observe     → memory:write
/agentmemory/migrate     → memory:admin
...（para la lista completa, consulte la API oficial de agentmemory）
```

### Cuando se utiliza en la misma máquina

Cuando `allow_loopback_bypass: true`, desde loopback (127.0.0.1) pasa sin clave API. **No es necesario** cambiar la configuración de MCP.

### Cuando se utiliza desde otra máquina en LAN

`@agentmemory/mcp` envía la variable de entorno `AGENTMEMORY_SECRET` como `Authorization: Bearer <secret>` hacia arriba.

**Ejemplo de cambio de configuración de MCP (`claude_desktop_config.json` / `.mcp.json`):**

```json
{
  "agentmemory": {
    "command": "npx",
    "args": ["-y", "@agentmemory/mcp"],
    "env": {
      "AGENTMEMORY_URL": "http://<gateway-host>:5000/agentmemory",
      "AGENTMEMORY_SECRET": "<api-key-secret>"
    }
  }
}
```

Alcances requeridos (especificar al crear la clave API):

```json
"scopes": ["memory:read", "memory:write"]
```

Si también se requieren operaciones administrativas (`/migrate`, `/governance/*`, etc.), añada `memory:admin`.

### Prueba de Funcionamiento

```bash
GW=http://<gateway-host>:5000
KEY=<api-key-secret>

# Sin autenticación (livez)
curl $GW/agentmemory/livez

# Obtener memories con Bearer
curl -H "Authorization: Bearer $KEY" "$GW/agentmemory/memories?limit=3"

# Funciona también con autenticación Basic (compatible con cliente SD)
curl -u "user:$KEY" "$GW/agentmemory/health"
```

---

## Modos de Autenticación

| Modo | Comportamiento |
|---|---|
| `api_key` | Token Bearer requerido (con `allow_loopback_bypass: true` loopback está exento) |
| `loopback` | Sin autenticación desde loopback (127.0.0.1). Desde LAN equivale a `api_key` |
| `none` | Sin autenticación (solo desarrollo/pruebas. NO para producción) |

Al establecer `allow_loopback_bypass: true`, herramientas en la misma máquina (como Claude Code CLI) pueden pasar a través de Gateway sin clave API.

---

## Sonda de Salud

Cuando `health_probe.enabled: true`, realiza comprobaciones automáticas de conectividad a backends en el intervalo configurado.

```json
"health_probe": {
  "enabled": true,
  "interval_seconds": 10
}
```

Los backends sin conexión se reportan en `/v1/router/capabilities` con `"status": "offline"` en el campo `backends`.

---

## Problemas Comunes

| Síntoma | Causa / Solución |
|---|---|
| Todas las solicitudes devuelven 401 | `allow_loopback_bypass` es `false` y loopback también requiere clave. O el valor Bearer es incorrecto |
| Proxy a SD WebUI devuelve 404 | El puerto en `sd_webui.base_url` es incorrecto (default 7860). Ejecute Probe en `/gateway` |
| WebSocket de ComfyUI no se conecta | Verifique que `ws_url` está configurado (`ws://127.0.0.1:8188/ws`) |
| Proxy de Gradio devuelve 404 | Verifique que `backend_name` coincida con la clave de backends en `config.json`. También se requiere especificar `type: "gradio"` |
| Flujo SSE de Gradio agota timeout | Generaciones prolongadas (video, etc.) tienen limitación de buffer completo. Inferencia corta (TTS, etc.) sin problemas |
| Alcance insuficiente devuelve 403 | La clave utilizada no tiene alcances suficientes. Añada desde gestión de claves API con una clave de alcance `*` |
| Solo permitir modelos específicos con `allowed_models` | Especifique como matriz: `"allowed_models": ["qwen2.5:7b", "llama3.3:70b"]` |

---

## No-Goals (Fuera del Alcance de Phase 1)

- Iniciar/detener/reiniciar backends (usar SSH + systemctl)
- `/v1/responses` (fachada compatible con Codex) — Phase 2 en adelante
- Balanceo de carga entre múltiples instancias de Gateway — usar inferencia distribuida de LAN Cowork

---

## Documentación Relacionada

- [Referencia de API de Gateway](../api/gateway.md) — detalles de puntos finales `/api/gateway/*`
- [Configuración de LLM Router](../llm-router/setup.md) — proxy ligero solo para LLM
- [Descripción General de LAN Cowork](../lan-cowork/README.md) — coordinación de múltiples nodos

## Gestión de Claves API en la Interfaz Web

Desde la pestaña **"Claves API de Gateway"** en la página de configuración, puede crear, listar y eliminar claves API.
También hay un enlace en la [página Gateway](/gateway).

### Crear una Clave API

1. Ingrese un **Etiqueta** (ejemplo: `Claude Desktop`) — el ID se genera automáticamente como slug (ejemplo: `claude-desktop`)
2. Seleccione **Alcances** con insignias (se requiere al menos uno)
3. Si selecciona `*` (permitir todo), marque la casilla de confirmación
4. Haga clic en el botón "Crear"
5. Copie el secreto mostrado — **una vez que deja esta pantalla, nunca se mostrará de nuevo**

### Notas Importantes

- La última clave con alcance `*` no puede eliminarse (prevención de bloqueo de Bearer)
- Cree primero una clave `*` diferente antes de eliminar

### Cómo Usar

```bash
curl -H "Authorization: Bearer <secret>" http://localhost:5000/v1/chat/completions ...
```
