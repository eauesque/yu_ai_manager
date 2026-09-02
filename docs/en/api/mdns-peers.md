# API: /api/mdns (Peer Discovery)

> Target version: v4.64.0 and later (Hailo extensions: v4.66.0 and later)

API for yu_ai_manager nodes on a LAN to discover each other via mDNS (`_yu-ai._tcp.local.`). There are two endpoints.

---

## GET /api/mdns/identity

### Overview

A self-introduction endpoint for a node. Other nodes call this during peer verification to confirm that the information advertised via mDNS belongs to a genuine yu_ai_manager instance.

### Authentication

**Authentication bypass (not required).** Authentication is intentionally omitted as this endpoint is used for mutual peer verification. The response contains only information already publicly available via mDNS. No secrets or sensitive information are included.

### Response

```json
{
  "product": "yu_ai_manager",
  "node_id": "a1b2c3d4-...",
  "version": "4.66.0",
  "capabilities": ["hailo"],
  "hailo_ollama_url": "http://192.168.1.10:11434"
}
```

| Field | Type | Description |
|---|---|---|
| `product` | string | Always `"yu_ai_manager"` |
| `node_id` | string | Unique UUID of the node |
| `version` | string | Application version (read from the VERSION file) |
| `capabilities` | string[] | List of available capabilities. Currently only `"hailo"` |
| `hailo_ollama_url` | string (optional) | LAN access URL for Hailo-Ollama. Not included if the LAN IP cannot be determined |

**Condition for `capabilities` to include `"hailo"`:** The `"hailo-local"` backend is registered in the LLM Router catalog.

**Condition for `hailo_ollama_url` to be included:** The `"hailo-ollama-local"` backend is registered in the catalog and a LAN IP can be determined. Loopback addresses (`127.0.0.1`, etc.) are rewritten to the LAN IP.

---

## GET /api/mdns/peers

### Overview

Returns a list of LAN peers discovered by this node. Intended for mDNS subsystem status checking and debugging.

### Authentication

**Authentication bypass (not required).** The response contains only information already broadcast on the LAN via mDNS.

### Response (Normal)

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

| Field | Type | Description |
|---|---|---|
| `running` | bool | Whether the mDNS subsystem is running |
| `status` | string | Subsystem status string |
| `self_node_id` | string | This node's node_id |
| `peers` | object[] | List of discovered peers (see table below) |

**peers elements:**

| Field | Type | Description |
|---|---|---|
| `node_id` | string | Unique UUID of the peer |
| `hostname` | string | mDNS hostname |
| `version` | string | Peer's application version |
| `llm_base_url` | string \| null | Peer's LLM endpoint URL |
| `llm_provider` | string \| null | LLM provider name (e.g. `"ollama"`) |
| `capabilities` | string[] | Peer's capability list |
| `web_port` | int \| null | Peer's WebUI port |
| `addresses` | string[] | Peer's LAN IP addresses |
| `hailo_ollama_url` | string \| null | Peer's Hailo-Ollama URL |
| `first_seen` | float \| null | Time of first discovery (Unix timestamp) |
| `last_seen` | float \| null | Time of last verification (Unix timestamp) |

### Response (mDNS Not Initialized)

```json
{
  "running": false,
  "reason": "mdns subsystem not initialised (disabled or init failed)",
  "peers": []
}
```

When `running: false`, mDNS is either disabled or initialization failed. Check the configuration and startup logs.

---

## Debug Mode

Start yu with the environment variable `TAGDB_DEBUG_TRUSTED_PEERS=1` to include additional fields in the `/api/mdns/peers` response.

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

| Field | Description |
|---|---|
| `trusted_ips` | List of IPs registered in the trusted IP registry |
| `bridge.managed_aliases` | List of aliases managed by the mDNS bridge |
| `bridge.config_aliases` | List of aliases statically defined in config |
| `bridge.cooldown_seconds_remaining` | Cooldown remaining seconds keyed by the first 8 characters of node_id |

**Warning:** `trusted_ips` could serve as an attack target list, so it is not exposed by default. Do not set `TAGDB_DEBUG_TRUSTED_PEERS=1` in production environments.

---

## mDNS Discovery Flow

```
Other node starts
    │
    ▼
Advertises mDNS _yu-ai._tcp.local.
    │
    ▼
LlmRouterMdnsBridge receives on_peer_added()
    │
    ▼
HTTP verification via GET /api/mdns/identity
    │
    ├─ Success → Register in PeerRegistry / BackendCatalog
    └─ Failure → Retry after cooldown
```

---

## Related Files

- `routes/mdns_identity.py` -- Endpoint implementation
- `core/mdns/` -- mDNS service / address utilities
- `core/llm_router/state.py` -- BackendCatalog
- `core/web/trusted_peer_registry.py` -- Trusted IP registry
- `docs/en/mesh-inference/overview.md` -- Overall mesh inference architecture
