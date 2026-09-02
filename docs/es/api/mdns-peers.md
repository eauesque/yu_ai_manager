# API: /api/mdns (Descubrimiento de Pares)

> Versión objetivo: v4.64.0 y posteriores (Extensiones Hailo: v4.66.0 y posteriores)

API para que los nodos de yu_ai_manager en una LAN se descubran entre sí a través de mDNS (`_yu-ai._tcp.local.`). Hay dos endpoints.

---

## GET /api/mdns/identity

### Descripción General

Un endpoint de auto-presentación para un nodo. Otros nodos lo llaman durante la verificación de pares para confirmar que la información anunciada a través de mDNS pertenece a una instancia genuin de yu_ai_manager.

### Autenticación

**Sin autenticación** (no requerida). La autenticación se omite intencionalmente ya que este endpoint se utiliza para verificación mutua de pares. La respuesta contiene solo información que ya está disponible públicamente a través de mDNS. No se incluye información de secretos o sensible.

### Respuesta

```json
{
  "product": "yu_ai_manager",
  "node_id": "a1b2c3d4-...",
  "version": "4.66.0",
  "capabilities": ["hailo"],
  "hailo_ollama_url": "http://192.168.1.10:11434"
}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `product` | string | Siempre `"yu_ai_manager"` |
| `node_id` | string | UUID único del nodo |
| `version` | string | Versión de la aplicación (leída del archivo VERSION) |
| `capabilities` | string[] | Lista de capacidades disponibles. Actualmente solo `"hailo"` |
| `hailo_ollama_url` | string (opcional) | URL de acceso LAN para Hailo-Ollama. No se incluye si no se puede determinar la IP de LAN |

**Condición para que `capabilities` incluya `"hailo"`:** El backend `"hailo-local"` está registrado en el catálogo del Router LLM.

**Condición para que se incluya `hailo_ollama_url`:** El backend `"hailo-ollama-local"` está registrado en el catálogo y se puede determinar una IP de LAN. Las direcciones de loopback (`127.0.0.1`, etc.) se reescriben a la IP de LAN.

---

## GET /api/mdns/peers

### Descripción General

Devuelve una lista de pares de LAN descubiertos por este nodo. Destinado a verificación de estado del subsistema mDNS y depuración.

### Autenticación

**Sin autenticación** (no requerida). La respuesta contiene solo información que ya se transmite en la LAN a través de mDNS.

### Respuesta (Normal)

```json
{
  "running": true,
  "status": "browsing",
  "self_node_id": "a1b2c3d4-...",
  "peers": [
    {
      "node_id": "e5f6a7b8-...",
      "hostname": "raspberrypi.local",
      "version": "4.66.0",
      "llm_base_url": "http://192.168.1.20:11434",
      "llm_provider": "ollama",
      "capabilities": ["hailo"],
      "web_port": 5000,
      "addresses": ["192.168.1.20"],
      "hailo_ollama_url": "http://192.168.1.20:11434",
      "first_seen": 1712600000.0,
      "last_seen": 1712603600.0
    }
  ]
}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `running` | bool | Si el subsistema mDNS está ejecutándose |
| `status` | string | Cadena de estado del subsistema |
| `self_node_id` | string | node_id de este nodo |
| `peers` | object[] | Lista de pares descubiertos (ver tabla a continuación) |

**Elementos de peers:**

| Campo | Tipo | Descripción |
|---|---|---|
| `node_id` | string | UUID único del par |
| `hostname` | string | Nombre de host mDNS |
| `version` | string | Versión de aplicación del par |
| `llm_base_url` | string \| null | URL del endpoint LLM del par |
| `llm_provider` | string \| null | Nombre del proveedor LLM (p. ej. `"ollama"`) |
| `capabilities` | string[] | Lista de capacidades del par |
| `web_port` | int \| null | Puerto WebUI del par |
| `addresses` | string[] | Direcciones IP de LAN del par |
| `hailo_ollama_url` | string \| null | URL Hailo-Ollama del par |
| `first_seen` | float \| null | Hora del primer descubrimiento (marca de tiempo Unix) |
| `last_seen` | float \| null | Hora de la última verificación (marca de tiempo Unix) |

### Respuesta (mDNS No Inicializado)

```json
{
  "running": false,
  "reason": "mdns subsystem not initialised (disabled or init failed)",
  "peers": []
}
```

Cuando `running: false`, mDNS está deshabilitado o la inicialización falló. Verifique la configuración y los registros de inicio.

---

## Modo de Depuración

Inicie yu con la variable de entorno `TAGDB_DEBUG_TRUSTED_PEERS=1` para incluir campos adicionales en la respuesta `/api/mdns/peers`.

```json
{
  "running": true,
  "peers": [...],
  "trusted_ips": ["192.168.1.20", "192.168.1.30"],
  "bridge": {
    "managed_aliases": ["ollama-192.168.1.20"],
    "config_aliases": ["my-nas"],
    "cooldown_seconds_remaining": {
      "e5f6a7b8": 12.3
    }
  }
}
```

| Campo | Descripción |
|---|---|
| `trusted_ips` | Lista de IPs registradas en el registro de IP confiable |
| `bridge.managed_aliases` | Lista de alias administrados por el puente mDNS |
| `bridge.config_aliases` | Lista de alias definidos estáticamente en config |
| `bridge.cooldown_seconds_remaining` | Segundos restantes de enfriamiento indexados por los primeros 8 caracteres de node_id |

**Advertencia:** `trusted_ips` podría servir como lista de objetivo de ataque, por lo que no se expone por defecto. No establezca `TAGDB_DEBUG_TRUSTED_PEERS=1` en entornos de producción.

---

## Flujo de Descubrimiento mDNS

```
Otro nodo inicia
    │
    ▼
Anuncia mDNS _yu-ai._tcp.local.
    │
    ▼
LlmRouterMdnsBridge recibe on_peer_added()
    │
    ▼
Verificación HTTP a través de GET /api/mdns/identity
    │
    ├─ Éxito → Registrar en PeerRegistry / BackendCatalog
    └─ Fallo → Reintentar después de enfriamiento
```

---

## Archivos Relacionados

- `routes/mdns_identity.py` -- Implementación del endpoint
- `core/mdns/` -- Servicio mDNS / utilidades de direcciones
- `core/llm_router/state.py` -- BackendCatalog
- `core/web/trusted_peer_registry.py` -- Registro de IP confiable
- `docs/en/mesh-inference/overview.md` -- Arquitectura general de inferencia de malla
