# Gateway — LAN Authentication Boundary Guide

> Target version: Gateway Phase 1 (v4.75.0+) / Gradio support added (v4.255.11+)

## What is Gateway?

Gateway is a reverse proxy that protects access to authentication-less backend tools  
such as **SD WebUI, ComfyUI, Ollama, and Gradio apps** using **Bearer tokens + scope model**.

```
External clients / machines on LAN
    │
    │  Authorization: Bearer <api_key>
    ▼
 yu_ai_manager  (/v1/*, /sd/*, /comfy/*, /gradio/<name>/*)
 ┌────────────────────────────────────────────────────────┐
 │                      Gateway                          │
 │           scope check ──► backend selection           │
 └────────────────────────────────────────────────────────┘
    │          │            │            │
    ▼          ▼            ▼            ▼
 Ollama    SD WebUI     ComfyUI      Gradio
 :11434     :7860         :8188        :7861
```

### Differences from LLM Router

| | Gateway | LLM Router |
|---|---|---|
| **Target** | SD WebUI, ComfyUI, Ollama, Gradio together | LLM (Ollama) only |
| **Auth** | Scope-based Bearer required | loopback can bypass |
| **Proxy routes** | `/sd/*`, `/comfy/*`, `/v1/*`, `/gradio/<name>/*` | `/v1/*` only |
| **Use case** | Safely expose generation tools externally / over LAN | AI coding tool backend |

Both can be enabled on the same machine.

---

## Setup

### 1. Create the first API key (CLI)

```bash
uv run python -m core.gateway.cli create-key --id admin-local --scopes "*"
```

Output example:
```
id:      admin-local
secret:  gw_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
(This secret is shown only once. Copy it now.)
```

### 2. Add to config.json

```json
{
  "gateway": {
    "auth": {
      "mode": "api_key",
      "allow_loopback_bypass": true,
      "api_keys": [
        {
          "id": "admin-local",
          "secret_enc": "enc:v2:...",
          "scopes": ["*"],
          "allowed_models": null
        }
      ]
    },
    "backends": {
      "ollama":       {"type": "ollama",   "base_url": "http://127.0.0.1:11434"},
      "sd_webui":     {"type": "sd_webui", "base_url": "http://127.0.0.1:7860"},
      "comfyui":      {"type": "comfyui",  "base_url": "http://127.0.0.1:8188", "ws_url": "ws://127.0.0.1:8188/ws"},
      "irodori-tts":  {"type": "gradio",   "base_url": "http://127.0.0.1:7861"}
    },
    "health_probe": {"enabled": true, "interval_seconds": 10}
  }
}
```

> Use the encrypted value in `enc:v2:...` format output by the CLI for the `secret_enc` field.  
> Do not write plaintext secrets directly in config.json.

### 3. Restart and verify

```bash
GW_HOST=<this machine's LAN IP>
GW_PORT=5000
BEARER=<api-key-secret>

# 401 without auth
curl -i http://$GW_HOST:$GW_PORT/v1/models

# 200 with correct Bearer
curl http://$GW_HOST:$GW_PORT/v1/models \
  -H "Authorization: Bearer $BEARER"

# Backend capabilities
curl http://$GW_HOST:$GW_PORT/v1/router/capabilities \
  -H "Authorization: Bearer $BEARER"

# Node service list
curl http://$GW_HOST:$GW_PORT/v1/node/services \
  -H "Authorization: Bearer $BEARER"
```

---

## WebUI (/gateway page)

Management dashboard opened at `/gateway`.

### Backend list

Displays the status of registered backends.

| Column | Description |
|---|---|
| **Type** | Backend type (`ollama`, `sd_webui`, `comfyui`, `gradio`) |
| **Port** | Proxy destination port number |
| **State** | `online` / `offline` / `unknown` |
| **Actions** | Probe (connectivity check), settings |

### Auto-scan backends

Click the Scan button to auto-detect running tools on common local ports  
(7860, 8188, 11434, 7861, etc.) and propose registration.

### API key management

You can also add and revoke API keys from the WebUI (requires a key with `*` scope).

---

## Scope Reference

| Scope | Permitted endpoints |
|---|---|
| `llm:chat` | `POST /v1/chat/completions` |
| `llm:messages` | `POST /v1/messages` (Anthropic-compatible) |
| `llm:models` | `GET /v1/models` |
| `sd:generate` | `POST /sd/sdapi/v1/txt2img` etc. |
| `sd:query` | `GET /sd/sdapi/v1/samplers` etc. |
| `sd:admin` | `POST /sd/sdapi/v1/options` etc. |
| `comfy:generate` | `POST /comfy/api/prompt` etc. |
| `comfy:query` | `GET /comfy/api/queue` etc. |
| `memory:read` | `GET /agentmemory/memories` etc. (read) |
| `memory:write` | `POST /agentmemory/observe` etc. (write) |
| `memory:admin` | `POST /agentmemory/migrate` etc. (admin) |
| `ollama:proxy` | `GET/POST /ollama/<name>/*` (Ollama native API + OpenAI-compat, full pass-through) |
| `gradio:proxy` | `GET/POST /gradio/<name>/*` (full pass-through) |
| `gateway:admin` | API key management and config changes (auto-granted to loopback) |
| `node:status` | `GET /v1/node/services` |
| `*` | All scopes (admin only) |

### Example keys by use case

```json
"api_keys": [
  {
    "id": "claude-code",
    "secret_enc": "enc:v2:...",
    "scopes": ["llm:chat", "llm:messages", "llm:models"],
    "allowed_models": null
  },
  {
    "id": "comfy-client",
    "secret_enc": "enc:v2:...",
    "scopes": ["comfy:generate", "comfy:query"],
    "allowed_models": null
  }
]
```

---

## Ollama Proxy

A transparent proxy for the full Ollama API — both native (`/api/*`) and OpenAI-compatible (`/v1/*`) —  
separate from the LLM Router's `/v1/*`. Point `OLLAMA_HOST` at Gateway to add authentication.

### Proxy URL

```
/ollama/<backend_name>/<subpath>  →  registered base_url/<subpath>
```

### Configuration example

```json
"backends": {
  "ollama": {"type": "ollama", "base_url": "http://127.0.0.1:11434"}
}
```

### Client setup (`OLLAMA_HOST`)

```bash
export OLLAMA_HOST=http://<gateway-host>:5000/ollama/ollama
# All subsequent ollama commands go through Gateway
ollama list
ollama run llama3.3:70b
```

> Clients that cannot pass a Bearer token can use `allow_loopback_bypass: true` from loopback,  
> or a key with `*` scope as a workaround.

### Large file transfer

Model blobs (`/api/blobs/*`) are streamed with no timeout (other paths: 300 s).  
GB-scale model pulls and pushes work without issues.

---

## Gradio Proxy

Exposes Gradio-based WebUIs (e.g. Irodori-TTS) through Gateway with Bearer authentication.  
Minimal implementation: full pass-through with a 50 MiB body limit only (no endpoint allow-list).

### Proxy URL

```
/gradio/<backend_name>/<subpath>  →  registered base_url/<subpath>
```

`<backend_name>` must match a key in the `backends` section of `config.json`.

### Configuration example

```json
"backends": {
  "irodori-tts": {"type": "gradio", "base_url": "http://127.0.0.1:7861"}
}
```

### Verification

```bash
GW=http://localhost:5000
KEY=<api-key-secret>

# Gradio app root
curl -H "Authorization: Bearer $KEY" "$GW/gradio/irodori-tts/"

# Gradio 3.x predict
curl -H "Authorization: Bearer $KEY" \
  -X POST "$GW/gradio/irodori-tts/run/predict" \
  -H "Content-Type: application/json" \
  -d '{"data": ["Hello"], "fn_index": 0}'
```

### Limitations

- WebSocket (`/queue/join`) is not supported — HTTP only
- Gradio 4.x SSE streams (`GET /call/{api_name}/{event_id}`) are fully buffered,  
  which may timeout for long-running generation (video, etc.)

---

## Agent Memory (agentmemory) Proxy

Gateway also provides a proxy for `@agentmemory/mcp` and other agentmemory clients  
to securely access over LAN.

### Endpoints

```
/agentmemory/livez       → No auth required (health check)
/agentmemory/health      → Requires memory:read scope
/agentmemory/memories    → memory:read
/agentmemory/observe     → memory:write
/agentmemory/migrate     → memory:admin
...（for complete list, see agentmemory official API）
```

### Same machine

With `allow_loopback_bypass: true`, loopback (127.0.0.1) requests bypass auth entirely.  
No MCP configuration changes needed.

### Remote machine (LAN)

`@agentmemory/mcp` reads the `AGENTMEMORY_SECRET` environment variable  
and sends it as `Authorization: Bearer <secret>` upstream.

**MCP config update example (`claude_desktop_config.json` / `.mcp.json`):**

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

Required scopes (specify when creating the key):

```json
"scopes": ["memory:read", "memory:write"]
```

Add `memory:admin` if you need migration or governance endpoints.

### Verification

```bash
GW=http://<gateway-host>:5000
KEY=<api-key-secret>

# No auth required (livez)
curl $GW/agentmemory/livez

# Get memories with Bearer
curl -H "Authorization: Bearer $KEY" "$GW/agentmemory/memories?limit=3"

# Basic auth also works (SD client compatible)
curl -u "user:$KEY" "$GW/agentmemory/health"
```

---

## Auth Modes

| Mode | Behavior |
|---|---|
| `api_key` | Bearer token required (`allow_loopback_bypass: true` exempts loopback only) |
| `loopback` | No auth from loopback (127.0.0.1). LAN requires `api_key` equivalent |
| `none` | No auth (dev/test only, not production) |

Setting `allow_loopback_bypass: true` allows tools on the same machine  
(such as Claude Code CLI) to pass through Gateway without API keys.

---

## Health Probe

When `health_probe.enabled: true`, backends are automatically probed  
at the configured interval.

```json
"health_probe": {
  "enabled": true,
  "interval_seconds": 10
}
```

Offline backends are reported as `"status": "offline"`  
in the `/v1/router/capabilities` response.

---

## Common Issues

| Symptom | Cause / Solution |
|---|---|
| All requests return 401 | `allow_loopback_bypass` is `false` so loopback also requires a key. Or Bearer value is incorrect |
| SD WebUI proxy returns 404 | Incorrect port in `sd_webui.base_url` (default: 7860). Run Probe from `/gateway` |
| ComfyUI WebSocket won't connect | Verify `ws_url` is configured (`ws://127.0.0.1:8188/ws`) |
| Gradio proxy returns 404 | `<backend_name>` must match the key in `config.json` backends. Also requires `"type": "gradio"` |
| Gradio SSE stream times out | Full-buffer limitation for long-running generation (video, etc.). Short tasks (TTS, etc.) are unaffected |
| 403 for insufficient scopes | API key scopes are insufficient. Use a key with `*` scope to add new keys via the API key management |
| Want to restrict to specific models via `allowed_models` | Specify as an array: `"allowed_models": ["qwen2.5:7b", "llama3.3:70b"]` |

---

## Non-Goals (Phase 1 scope)

- Backend start/stop/restart (use SSH + systemctl)
- `/v1/responses` (Codex-compatible façade) — Phase 2+
- Load balancing across multiple Gateway instances — use LAN Cowork distributed inference

---

## Related Documentation

- [Gateway API Reference](../api/gateway.md) — Details on `/api/gateway/*` endpoints
- [LLM Router Setup](../llm-router/setup.md) — Lightweight LLM-only proxy
- [LAN Cowork Overview](../lan-cowork/README.md) — Multi-node coordination

## API Key Management via WebUI

From the Settings page **"Gateway API Keys"** tab, create, list, and delete keys.  
A link is also available on the [Gateway page](/gateway).

### Creating an API Key

1. Enter a **Label** (example: `Claude Desktop`) — ID is auto-slugified (example: `claude-desktop`)
2. Select **scopes** via badges (at least one required)
3. When selecting `*` (full access), check the confirmation checkbox
4. Click **Create** and copy the secret — **never displayed again after leaving this screen**

### Notes

- The last key with `*` scope cannot be deleted (prevents Bearer lockout)
- Create another `*` key first before deleting the old one

### Usage

```bash
curl -H "Authorization: Bearer <secret>" http://localhost:5000/v1/chat/completions ...
```
