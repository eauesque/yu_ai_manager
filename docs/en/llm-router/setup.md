# LLM Router Setup

## Adding to config.json

```json
{
  "llm_router": {
    "enabled": true,
    "auth": {
      "mode": "loopback",
      "api_key": "",
      "allow_loopback_bypass": true
    },
    "backends": [
      {
        "alias": "ollama-local",
        "base_url": "http://localhost:11434/v1",
        "type": "ollama",
        "auto_discover": true
      }
    ],
    "aliases": {
      "local-fast": "ollama-local/qwen2.5:7b",
      "local-coder": "ollama-local/qwen2.5-coder:32b"
    }
  }
}
```

## Integration with Claude Code

LLM Router implements the Anthropic-compatible `/v1/messages` endpoint, so
Claude Code (the official Anthropic CLI) can talk to your local LLMs **directly**.
No extra proxy (claude-code-router etc.) is needed.

### 1. Alias setup on yu_ai_manager

Claude Code internally sends model names like `claude-opus-4-*` /
`claude-sonnet-4-*` / `claude-haiku-4-*`. Map them to local categories
(`large` / `fast` / `vision`) or physical models in `config.json`:

```json
{
  "llm_router": {
    "enabled": true,
    "aliases": {
      "claude-opus-4-7":           "large",
      "claude-sonnet-4-6":         "fast",
      "claude-haiku-4-5":          "fast",
      "claude-3-5-haiku-20241022": "fast"
    }
  }
}
```

| Model name from Claude Code | Recommended target | Purpose |
|---|---|---|
| `claude-opus-*` | `large` (e.g. qwen2.5:72b / llama3.3:70b) | Main reasoning |
| `claude-sonnet-*` | `fast` or `large` | Balanced |
| `claude-haiku-*` | `fast` (e.g. qwen2.5:7b) | Background tasks (summaries, titles) |

`large` / `fast` / `vision` are virtual backends from the `core/llm_core`
category registry; the actual model is picked from registered candidates
(visible in the `/llm-router` WebUI).

### 2. Claude Code configuration

Add to `~/.claude/settings.json` (Windows: `%USERPROFILE%\.claude\settings.json`):

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:5000/v1",
    "ANTHROPIC_AUTH_TOKEN": "dummy"
  }
}
```

- `ANTHROPIC_AUTH_TOKEN` is not validated for loopback access, but Claude Code
  requires the variable to exist — any string works
- To reach a yu_ai_manager on another LAN host, change to
  `http://<host>.local:5000/v1` and switch `auth.mode` to `api_key` with a real token

For one-off testing via shell:

```bash
ANTHROPIC_BASE_URL=http://localhost:5000/v1 ANTHROPIC_AUTH_TOKEN=dummy claude
```

### 3. Routing the background (haiku-equivalent) model separately

Claude Code's background tasks can be overridden via `ANTHROPIC_SMALL_FAST_MODEL`:

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:5000/v1",
    "ANTHROPIC_AUTH_TOKEN": "dummy",
    "ANTHROPIC_SMALL_FAST_MODEL": "fast"
  }
}
```

Main traffic goes through the alias map (opus → large), background traffic
explicitly hits the `fast` category.

### 4. Verification

```bash
# Does /v1/messages respond?
curl -s http://localhost:5000/v1/messages \
  -H "content-type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -d '{"model":"claude-opus-4-7","max_tokens":64,"messages":[{"role":"user","content":"ping"}]}'

# From Claude Code
claude
> /model          # check active model
> hello           # any response = local routing works
```

### 5. Common pitfalls

| Symptom | Cause / fix |
|---|---|
| `model_not_found` error | Claude Code's model name matches neither an alias nor a category. Check the request log in `/llm-router` WebUI and add the alias |
| Very slow responses | `large` resolved to a 70B-class model. Map the alias to a specific lighter model |
| `401 unauthorized` | `auth.mode` is `api_key` and Claude Code's `ANTHROPIC_AUTH_TOKEN` doesn't match |
| Stream cuts off mid-response | Backend (e.g. Ollama) timeout too short. Set `backends[].timeout` to ≥120 in `config.json` |

### 6. Specifying physical / custom aliases directly

The `aliases` section accepts any name, not just Claude model names:

```json
"aliases": {
  "local-fast":  "ollama-local/qwen2.5:7b",
  "local-coder": "ollama-mac/qwen2.5-coder:32b"
}
```

Then `/model local-coder` in Claude Code routes straight to that model.

### 7. Hybrid setup (opus on real Anthropic, sonnet/haiku local) — current limits

Splitting traffic so that "the orchestrator runs on Anthropic's opus, only
sub-agents go to local" is **not recommended** with Claude Code + LLM Router today:

- `ANTHROPIC_BASE_URL` applies to the entire session, so there is no Claude Code
  setting that lets only opus requests pass through to Anthropic
- A passthrough backend in LLM Router would be technically feasible, but the
  economics don't work out:
  - **Max/Pro subscription users**: setting `ANTHROPIC_BASE_URL` drops you out
    of the subscription auth path, so passthrough opus calls get billed at API
    rates (more expensive, not less)
  - **API-key billed users**: passthrough doesn't change opus per-token pricing,
    and orchestrator opus tokens dominate the bill — moving sub-agents local
    saves little

**Recommendation**: if cost reduction is the goal, **route everything to local**
(map `claude-opus-*` to the `large` category as well) and rely on a strong local
model (Qwen2.5-72B / Llama 3.3-70B / DeepSeek etc.) for quality. With proper
role separation between orchestrator and implementation agents, 70B-class
models are usually capable enough.

This section will be revisited if Claude Code gains per-model endpoint
overrides (e.g. `ANTHROPIC_OPUS_BASE_URL`).

## Integration with Continue (VSCode)

`config.json`:
```json
{
  "models": [
    {
      "title": "Local Coder",
      "provider": "openai",
      "apiBase": "http://localhost:5000/v1",
      "model": "local-coder",
      "apiKey": "dummy"
    }
  ]
}
```

## Node Auto-discovery -- `.local` Hostname Support (Home LAN)

When running multiple machines on a home LAN (e.g. Mac mini + Pi5 + Windows GPU machine), you can use `.local` hostnames instead of IP addresses in `base_url`. This way, **the configuration keeps working even if DHCP reassigns IP addresses**. No additional implementation is needed on the yu_ai_manager side -- `httpx` resolves names automatically through the OS resolver (Bonjour / Avahi / mDNSResponder).

```json
{
  "llm_router": {
    "enabled": true,
    "backends": [
      { "alias": "ollama-mac", "base_url": "http://mac-mini.local:11434/v1", "type": "ollama" },
      { "alias": "ollama-pi5", "base_url": "http://pi5.local:11434/v1",      "type": "ollama" },
      { "alias": "ollama-win", "base_url": "http://gpu-rig.local:11434/v1",  "type": "ollama" }
    ],
    "aliases": {
      "local-fast":  "ollama-mac/qwen2.5:7b",
      "local-coder": "ollama-pi5/qwen2.5-coder:32b",
      "local-big":   "ollama-win/llama3.3:70b"
    }
  }
}
```

Sample: [`config.example.local-hostname.json`](../../../config.example.local-hostname.json)

### Requirements

| OS | Required |
|---|---|
| macOS | Bonjour (built-in, no additional installation needed) |
| Linux | `avahi-daemon` (`sudo apt install avahi-daemon` / `sudo systemctl enable --now avahi-daemon`) |
| Windows 10/11 | mDNSResponder (Win10 1803 and later can resolve `.local` natively. If it doesn't work, install Bonjour Print Services) |

### Verification

```bash
# Test that resolution works
python -c "import socket; print(socket.gethostbyname('mac-mini.local'))"
# → If it returns 192.168.x.x, it's working
```

### Cross-subnet / Corporate LAN / VPN

mDNS operates via L2 multicast, so **it cannot reach across routers, VPNs, or isolated VLANs in corporate networks**. In these environments, specify IP addresses directly as before:

```json
"backends": [
  { "alias": "remote-gpu", "base_url": "http://10.20.30.40:11434/v1", "type": "ollama" },
  { "alias": "tailscale-mac", "base_url": "http://100.x.x.x:11434/v1", "type": "ollama" }
]
```

If you need an mDNS reflector in a VLAN-segmented environment, consult your LAN administrator. yu_ai_manager does not provide an mDNS reflector or proxy.

### Known Limitations

- **Windows mDNS resolution can occasionally be slow** (~1 second): It is recommended to set the backend `timeout` to 3 seconds or more
- **`.local` suffix is required**: Using `mac-mini` alone will fall back to NetBIOS / DNS, so always write `mac-mini.local`
- **Ollama does not advertise via mDNS**: Only hostname resolution is used; the port (11434) must be specified manually. For yu-collocated Ollama, v4.71.0 adds an `_ollama._tcp.local.` advertiser on the yu side. For pure bare Ollama nodes (no yu), see "Handling of Pure Bare Ollama Nodes (without co-hosted yu)" below for the policy

## Environment Variables

| Variable | Behavior |
|---|---|
| `TAGDB_DISABLE_LLM_ROUTER` | Set to `1` to disable the entire Router |
| `TAGDB_DISABLE_LLM_ROUTER_REFRESH` | Set to `1` to disable the 5-minute refresh loop |
| `TAGDB_LLM_ROUTER_AUTH_MODE` | Override with `none`/`loopback`/`api_key` |

## Multi-language Documentation

Following the `docs/ reading rules` in CLAUDE.md, `en/zh-tw/zh-cn/ko` versions are synchronized based on the `ja/` source (as a separate task after implementation; see TODO.md).

## Node Auto-discovery (Phase B -- v4.64.0 and later)

yu_ai_manager nodes on the same LAN automatically discover each other via mDNS (`_yu-ai._tcp.local.`). Even without manually writing backends in `config.json`, discovered nodes are automatically registered in the `BackendCatalog` with `mdns-<prefix>` aliases.

### How It Works

1. On startup, `core/mdns/` advertises `_yu-ai._tcp.local.`
2. It subscribes to other nodes' TXT records and verifies that the required keys (version/node_id/llm_base_url) are present
3. For nodes with a matching major version, it sends an HTTP GET to `http://<addr>:<web_port>/api/mdns/identity` to confirm that product/node_id/version match
4. Verified nodes are registered in the LLM Router as `BackendInfo(alias="mdns-<node_id[:8]>")`
5. From there, the existing probe loop handles periodic refreshes

### Prerequisites

- The OS mDNS responder must be running (macOS: Bonjour, Linux: Avahi, Windows: mDNSResponder)
- Nodes must be on the same L2 subnet (for cross-router / VPN scenarios, use the manual config from Phase A)
- UDP 5353 must be allowed through the local firewall
- **Ollama must be exposed to the LAN** -- Ollama binds to `127.0.0.1:11434` by default, so it is unreachable from other nodes on the LAN. Set the environment variable `OLLAMA_HOST=0.0.0.0:11434` before starting Ollama (macOS: `launchctl setenv OLLAMA_HOST "0.0.0.0:11434"`, Linux: systemd unit / `.bashrc`, Windows: system environment variables). If this is not set, yu_ai_manager determines it is localhost-only and will not advertise `llm_base_url` (a warning will appear in the startup log)

### Ollama Auto-detection

If there is no localhost entry in `llm_router.backends` in `config.json`, yu_ai_manager searches for Ollama on startup in the following order:

1. `http://<LAN_IP>:11434/api/tags` -- Ollama reachable from the LAN
2. `http://localhost:11434/api/tags` -- Even if detected, LAN advertising is not performed (the above warning is displayed)

If a 200 response is returned from the LAN IP, it is automatically included as `llm_base_url` in the TXT record. This is intended for zero-configuration participation of Ollama co-hosted nodes via mDNS. Non-default ports (11435, etc.) or lmstudio / llamacpp still require explicit entries in `config.json`.

### Handling of Pure Bare Ollama Nodes (without co-hosted yu) (policy)

Pure bare Ollama nodes where `yu_ai_manager` is **not** running (e.g. a family
member's Mac that only has Ollama installed, or an Ollama container on a NAS)
are **not covered by auto-discovery**. `Ollama` itself has no feature that
advertises `_ollama._tcp.local.` officially, so there is structurally no way
to detect them.

To use such nodes from the LLM Router, configure them **manually** via one of:

```json
{
  "llm_router": {
    "backends": [
      { "alias": "ollama-nas",    "base_url": "http://nas.local:11434/v1",     "type": "ollama" },
      { "alias": "ollama-family", "base_url": "http://192.168.1.42:11434/v1", "type": "ollama" }
    ]
  }
}
```

- If your environment supports `.local` hostnames (see "Node Auto-discovery -- `.local` Hostname Support" above), prefer that
- Otherwise, hard-code the fixed IP

#### Why auto-discovery is not attempted

When designing this (2026-04-11), the following three options were compared, and option (c) manual config guidance was chosen:

| Option | Description | Decision |
|---|---|---|
| (a) Scan the entire LAN `:11434` at startup | Brute-force probe all hosts in the subnet | **Rejected** — heavy network load, disruptive on corporate / large LANs, may be mistaken for port scanning, contradicts the edge-first philosophy |
| (b) External Ollama advertiser daemon | Ship a lightweight yu-provided advertiser that runs alongside each Ollama host | **Rejected** — requires an extra resident process, which is equivalent to just installing `yu_ai_manager` itself. Defeats the point of "pure bare" |
| (c) Manual backend config via fixed IP / `.local` | Hand-written entries in `config.json` | **Chosen** — zero extra implementation, explicit behavior, avoids dragging users into unintended scans |

If Ollama upstream later advertises `_ollama._tcp.local.` officially, or adds
an official service discovery mechanism, we will revisit this as Phase D at that time.

### Disabling

You can disable auto-discovery in environments where it is not needed (Docker isolation, corporate LAN, CI, etc.):

- Add `"mdns": {"enabled": false}` to `config.json`
- Or set the environment variable `YU_AI_MDNS_DISABLED=1`

### Known Behaviors

- **Multi-homed environments (Wi-Fi + Ethernet)**: With the default setting (`bind_address: null`), advertising occurs on both interfaces and `PeerInfo.addresses` will contain multiple IPs. To restrict to a single interface, specify `"bind_address": "192.168.x.y"`.
- **Alias collision**: If a backend in `config.json` uses an alias in the `mdns-xxxxxxxx` format, the manual config takes priority and the mDNS-discovered entry is skipped.
- **Cross-subnet**: mDNS operates only within the L2 broadcast domain by default. For cross-subnet operation, use the `.local` hostname approach from Phase A.
- **Security**: mDNS itself has no authentication. It is designed for trusted environments such as home LANs. Disabling is recommended on public Wi-Fi or large shared networks. The `/api/mdns/identity` verification prevents accidental misidentification of nodes or mixing of incompatible older versions.
