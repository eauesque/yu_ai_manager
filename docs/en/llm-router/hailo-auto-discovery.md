# Hailo LLM Auto-discovery

**Supported version**: v4.66.0 and later

## Overview

yu_ai_manager can automatically discover and use LLM endpoints running on the Pi5's Hailo NPU without editing `config.json`. Simply plug a Pi5 into the LAN, and other yu_ai_manager nodes can call the Hailo LLM.

## Two Endpoint Types

| Endpoint | Description | Default URL Pattern |
|---|---|---|
| **yu extension Hailo LLM** | OpenAI-compatible LLM provided by the built-in `builtin-hailo-genai` extension in yu_ai_manager | `http://<host>:<yu-port>/ext/hailo-genai/v1/` |
| **hailo-ollama** | OpenAI-compatible LLM provided by the external binary `/usr/bin/hailo-ollama` (default port `:8000`) | `http://<host>:8000/v1/` |

Both can run simultaneously and both are auto-registered. With HailoRT 5.3.0+ and `HAILO_OLLAMA_VDEVICE_GROUP_ID=YU_SHARED` set, the HailoRT scheduler shares the physical device via round-robin, so there is no conflict when using both concurrently.

## Local Auto-registration (Phase A)

On startup, yu_ai_manager independently detects the following two endpoints:

1. **yu extension**: If `hailo_platform.genai.LLM` is importable and either `/dev/hailo0` or `/dev/h1x-0` exists, it is auto-registered as a `hailo-local` backend in the catalog
   (v4.66.1 added support for Raspberry Pi 5 + AI HAT + HailoRT 5.3.0 which exposes the device as `/dev/h1x-0`)
2. **hailo-ollama**: An HTTP probe is sent to `localhost:8000/v1/models` (2-second timeout). If a 200 response is received, it is auto-registered as a `hailo-ollama-local` backend

If a backend with the same alias already exists in `llm_router.backends` in `config.json`, that configuration takes priority (it will not be overwritten).

## mDNS Advertising (Phase B)

Based on the Phase A detection results, yu_ai_manager advertises Hailo capabilities to other nodes via mDNS TXT records:

- `capabilities=llm,hailo` -- Indicates that the yu extension is available
- `hailo_ollama_url=http://192.168.1.10:8000/v1/` -- Included only if hailo-ollama is running (rewritten to a LAN-reachable IP)

When other yu_ai_manager nodes receive this via mDNS, they perform identity verification through the `/api/mdns/identity` endpoint, then auto-register additional backends with the following aliases:

- `mdns-<node_id[:8]>-hailo` -- yu extension Hailo LLM (when `capabilities` includes `hailo`, the URL is derived from the peer's `web_port` + addresses)
- `mdns-<node_id[:8]>-hailo-ollama` -- External hailo-ollama (when `hailo_ollama_url` is advertised, the URL from the TXT record is used as-is)

## Configuration

Enabled by default. You can disable it in `config.json` as follows:

```json
{
  "llm_router": {
    "hailo_ollama": {
      "enabled": false,
      "port": 8000
    }
  }
}
```

- **`enabled`**: Set to `false` to completely disable hailo-ollama auto-detection. Detection of the yu extension is controlled separately (automatically determined by whether the extension is loaded)
- **`port`**: Port number for hailo-ollama (default 8000). Values outside the range 1--65535 fall back to the default with a warning log

## Security Notes

**hailo-ollama has no authentication**. When advertised via mDNS, **any node on the LAN can freely consume hailo-ollama's inference resources**.

| Endpoint | Authentication | Effective LAN Exposure |
|---|---|---|
| yu extension (`/ext/hailo-genai/v1/`) | yu's web auth chain (PIN/session/api-key) | Only clients authenticated with yu |
| hailo-ollama (`hailo_ollama_url`) | **None** | **All nodes on the LAN** |

For environments other than home LANs or trusted VLANs (e.g. public Wi-Fi), disable auto-advertising with `hailo_ollama.enabled: false`.

## Appearance in LLM Router WebUI

Auto-registered backends are displayed on the `/llm-router` dashboard (v4.65.0):

- `hailo-local` / `hailo-ollama-local` -- Locally detected (source: `static` badge)
- `mdns-<id>-hailo` / `mdns-<id>-hailo-ollama` -- Discovered via mDNS (source: `mdns` badge)

All can be temporarily disabled via the Disable toggle. The disabled state is persisted to `data/llm_router_state.json` and retained after restarts (implemented in v4.65.0).

## False-positive Safety

Phase A detection has two safety mechanisms:

1. **Self-probe avoidance**: If `hailo_ollama.port` is set to the same value as yu's own web port, the probe is skipped entirely (prevents yu from misidentifying itself as hailo-ollama)
2. **Existing backend priority**: If a backend with the same `localhost:<port>/v1` is already registered in `config.json`, the probe is skipped to respect the user's intent

## TODO Remaining Items

- (P3) Multi-language translations (`en`, `zh-tw`, `zh-cn`, `ko`) -- planned to be addressed together with the v4.65.0 LLM Router WebUI translation backlog
- (P3) Pi5 integration testing -- Playwright 16-item equivalent in a 2-node setup
- (P3) IPv6 support -- Currently `_pick_lan_ip` only returns IPv4
- (P3) Multiple Hailo device support -- Assumes a fixed `hailo-local` alias. Index suffix design to be considered for cases such as multiple USB dongles
- (P3) `BackendCatalog.remove_backend()` -- Currently `_mark_unreachable` only updates the status and does not remove from the catalog

## Related Documentation

- [LLM Router Setup](./setup.md)
- Design spec: `docs/superpowers/specs/2026-04-08-hailo-auto-discovery-design.md`
- Implementation plan: `docs/superpowers/plans/2026-04-08-hailo-auto-discovery.md`

## v4.66.2 -- Trusted Peer Auth (Fixing a Real-device Authentication Hole)

In v4.66.0's Hailo auto-discovery, yu's `/ext/hailo-genai/*` extension was behind the web auth chain. When the LLM Router driver (which has neither a Bearer token nor a session) tried to probe/dispatch, the auth middleware returned honeypot HTML, causing JSON parse failures and the backend getting stuck as `unreachable`.

### How It Works

- A new `TrustedPeerRegistry` seeds `127.0.0.1` / `::1` at init time
- When `LlmRouterMdnsBridge` successfully verifies a peer (HTTP GET to `/api/mdns/identity` + node_id match confirmation), all of that peer's advertised addresses are added to the registry
- `auth_chain.check_trusted_peer` bypasses PIN auth when receiving a request for `/ext/<name>/v1/*` paths if the remote_addr is in the registry
- Existing API key / session / cookie authentication paths remain unchanged

### Relationship with Quick Lock

- **loopback** (yu's own self-probe): Always passes, even during quick_lock
- **peer IP**: Requests are rejected during quick_lock (`check_quick_lock` returns 503). This means peers also respect the "user intentionally locked" state

This enables the following scenarios to work as expected:

- pi2's `hailo-local` self-probe (`http://localhost:5000/ext/hailo-genai/v1/models`)
- Cross-node dispatch from Windows to pi2's `mdns-<id>-hailo` (`http://192.168.50.4:5000/ext/hailo-genai/v1/chat/completions`)

### Configuration

No configuration file changes are needed. Even in environments where mDNS is disabled, the loopback seed still functions, so the self-probe fix is available unconditionally.

### Debugging

Set the environment variable `TAGDB_DEBUG_TRUSTED_PEERS=1` before starting yu to add a `trusted_ips` field to the `/api/mdns/peers` response. Do not set this in production (the trust list is essentially an "attack target list" and should not be exposed on unauthenticated endpoints).

### Security Boundary

Operating under the "trusted LAN" assumption (same premise as the v4.64.0 mDNS Phase B). Protection against malicious nodes with physical access to the LAN is out of scope -- use the `/llm-router` WebUI disable toggle or quick_lock for such cases.

See `docs/superpowers/specs/2026-04-09-trusted-peer-auth-design.md` for details.
