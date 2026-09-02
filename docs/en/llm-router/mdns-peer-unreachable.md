# mDNS Backend Stuck as "Unreachable"

This document covers the causes, diagnosis, and remediation for mDNS-discovered LLM Router backends that remain stuck in the "unreachable" state.

---

## Structural Overview

```
MdnsService (zeroconf layer)
  └─ on_peer_added / on_peer_updated / on_peer_removed
       └─ LlmRouterMdnsBridge
            ├─ _verify()       ← HTTP check against /api/mdns/identity
            ├─ _apply_peer_to_catalog()  ← registers in BackendCatalog
            ├─ _enter_cooldown() / _in_cooldown()  ← retry throttling after failure
            └─ retry_pending_peers()  ← 60-second periodic sweep (v4.91.15+)
```

**Key flow**:

1. zeroconf detects a peer → calls `on_peer_added`
2. `_verify()` hits `/api/mdns/identity` and validates `node_id` and `product`
3. Success → `_apply_peer_to_catalog()` adds the backend to the catalog
4. Failure → enters 60-second cooldown; same `node_id` events are ignored
5. **v4.91.15+**: A 60-second sweep task automatically retries unreachable peers after cooldown expires

---

## Common "Unreachable" Patterns

### Pattern A — Initial verify failure → silenced by cooldown

**Symptom**: Backend appears in LLM Router with status=unreachable.  
**Cause**:
- The remote node's HTTP server was not yet up when it was first discovered.
- Your port changed and the peer is referencing a stale TXT record (pre-v4.91.14 `--port` override bug; fixed in 35a3679a).

**Behavior (before v4.91.15)**: Once the cooldown (60 s) expires, the system waits for the next `on_peer_updated` event. If that event never fires, the backend never recovers.

**Behavior (v4.91.15+)**: After cooldown expires, the next sweep tick (within 60 seconds) automatically retries → on success the catalog is updated.

---

### Pattern B — zeroconf does not fire `ServiceStateChange.Updated`

**Symptom**: Peer restarted but LLM Router still shows the old status.  
**Cause**: Depending on zeroconf's cache state, `Updated` events may not fire on TXT record changes (known behavior of the zeroconf library).  
**Remediation**: The v4.91.15 sweep task picks this up within 60 seconds.

---

### Pattern C — Remote node's port differs from advertised value

**Symptom**: `curl` reaches the node but verify keeps timing out.  
**Cause**: Using `--port` CLI flag while `config.json`'s `server.port` is still the old value → wrong port is advertised in mDNS TXT.  
**Fix**: Resolved in v4.91.14 (35a3679a) by overwriting `config["server"]["port"]` with the effective port. If an old startup script writes config.json directly, also update that.

---

### Pattern D — Not registered in trusted_peer_registry

**Symptom**: LLM Router shows "ready" but proxied requests to `/ext/<name>/v1/*` return 403.  
**Cause**: The process restarted before `_apply_peer_to_catalog()` was called, or the peer has `service_kind != "yu"` so registry registration is intentionally skipped (bare Ollama peers are not registered).  
**Check**:
```bash
curl -s http://127.0.0.1:PORT/api/mdns/peers | python3 -m json.tool | grep -E 'node_id|trusted'
```

---

## Diagnosis Steps

### 1. Check current peer state

```bash
# List known peers
curl -s http://127.0.0.1:PORT/api/mdns/peers | python3 -m json.tool

# LLM Router backend list (mDNS-originated backends have alias starting with "mdns-")
curl -s http://127.0.0.1:PORT/api/llm_router/status | python3 -m json.tool
```

### 2. Verify the identity endpoint is reachable from the remote node

On the remote node:
```bash
curl -v http://<your-LAN-IP>:<PORT>/api/mdns/identity
```

Expected response:
```json
{"product": "yu_ai_manager", "node_id": "...", "version": "..."}
```

If it fails:
- Firewall / routing issue
- Port mismatch between effective port and advertised value (check if started with `--port`)

### 3. Check the advertised port

```bash
# Startup log should show "web_port"
grep -i "web_port\|mdns.*port\|effective_port" logs/app.log | tail -20

# Or via settings API
curl -s http://127.0.0.1:PORT/api/server/info | python3 -m json.tool | grep port
```

### 4. Check cooldown state

GUI: **LLM Router** > backend card > details — shows `last_error` and `last_seen_at`.  
If the error is "identity verification failed", the HTTP request reached the target but the content didn't match (node_id / product mismatch).  
If the error is "timeout", the HTTP request itself is not arriving.

### 5. Check sweep logs

```bash
grep "\[mdns\] sweep" logs/app.log
```

`sweep re-verified peer <8 chars>` indicates the sweep successfully recovered the peer.

---

## Forced Recovery (Manual)

To recover immediately without waiting for the sweep:

### Method 1: Restart the remote node

Restarting causes zeroconf to fire `ServiceStateChange.Removed` + `Added` → `on_peer_removed` clears the cooldown → `on_peer_added` immediately re-verifies.

### Method 2: Restart the mDNS service via the UI (if available)

**Settings** > **LLM Router** > **Restart mDNS** button.

### Method 3: Restart the application

Cooldown state only exists in memory. Restarting clears all cooldowns and re-verifies all peers immediately on startup.

---

## Prevention Checklist

| Check | How to verify |
|-------|---------------|
| When using `--port`, does config.json `server.port` match? | Check config.json |
| Is inbound traffic on `PORT` allowed by the firewall? | `sudo ufw status` / macOS System Settings |
| On multi-NIC systems, is the correct LAN interface bound? | `config.json` `mdns.bind_address` |
| Is v4.91.15+ in use (includes sweep task)? | `curl .../api/server/info` |

---

## Related Files

| File | Role |
|------|------|
| `core/llm_router/mdns_integration.py` | `LlmRouterMdnsBridge`, cooldown, `retry_pending_peers` |
| `core/web/runtime_mdns.py` | Sweep task start/stop |
| `core/mdns/service.py` | zeroconf wrapper, `list_peers()` |
| `core/web/trusted_peer_registry.py` | Cross-node `/ext/*` authentication |
