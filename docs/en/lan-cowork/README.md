# LAN Cowork

> Target version: v4.55.0 and later (PIN authentication available from v4.92.0 and later)

## What is LAN Cowork

LAN Cowork is an extension feature that enables coordination among multiple yu_ai_manager nodes on a network.  
Each machine operates independently while allowing heavy processing to be distributed or managed collectively as a Fleet.

```
┌──────────────┐     mDNS discovery    ┌──────────────┐
│  Windows PC  │◄───────────────────────►│   Mac Mini   │
│  (GPU enabled)│   PIN pairing         │ (Control)    │
│              │◄───────────────────────►│              │
│ Distributed  │                        │  Fleet       │
│ inference    │                        │  management  │
│ (tagger etc) │                        │              │
└──────────────┘                        └──────────────┘
        ▲                                       ▲
        └───────────────────────────────────────┘
                      ▼
              ┌──────────────┐
              │ Raspberry Pi │
              │ (Hailo NPU)  │
              └──────────────┘
```

---

## Feature Overview

| Feature | Description |
|---|---|
| **mDNS Auto-discovery** | Automatically discover nodes on the same LAN without configuration |
| **PIN Pairing** | Admin-approved PIN authentication for issuing inter-peer tokens |
| **Distributed Inference** | Parallel processing of tagger, clip, yolo, and whisper across multiple nodes |
| **Generation Distribution** | Delegate SD WebUI / ComfyUI jobs to LAN nodes |
| **Fleet Management** | Centrally manage logs and version updates across nodes |
| **Peer Event Relay** | Stream events from other nodes to your own node's SSE |
| **LLM Routing** | Automatically register discovered peers in LLM Router |

---

## Setup Steps

### 1. Enable

Add to `config.json`:

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "enabled": true,
      "peer_name": "my-desktop"
    }
  }
}
```

> **Note**: This page previously directed the activation key to the top-level `{"lan_cowork": {...}}`, but no implementation reads a key at that location. The `extensions` section above is the correct location.

> **The default depends on the backend:** the Python backend (hybrid) treats a missing key as **enabled**, while the Rust standalone server is **disabled** unless explicitly enabled. For what actually happens on the network once enabled, see [Network behavior](network-behavior.md).

After restart:
- Listen for other nodes on UDP 19850
- Start advertising _yu-ai._tcp.local. via mDNS

### 2. Pair Nodes

To connect from Node A to Node B:

1. **Node A WebUI** → `Settings` → `LAN Cowork` → Add Node B URL
2. Node A sends `POST /api/lan/pair/request`
3. **Node B WebUI** → `/lan-cowork/peers` → Approve in the "Pending Approval" tab
4. 6-digit PIN is sent to Node A (via SSE)
5. Node A enters PIN → Obtain Bearer token (valid for 30 days)

> **Note**: Pairing is one-directional. Perform both A→B and B→A.

See [Peer PIN Authentication and Token Pairing](peer-auth.md) for details.

### 3. Verify Operation

```bash
# List of discovered peers (from Node A)
curl http://localhost:5000/api/mdns/peers

# Peers recognized by LAN Cowork
curl http://localhost:5000/api/lan/peers
```

---

## Feature-specific Setup

### Distributed Inference

Distributed inference becomes available automatically after pairing is complete.

- `Settings` → `LAN Cowork` → Enable inference types (tagger/clip/yolo/whisper) for each node
- Or configure individually via the matrix on `/mesh-inference` page

Details: [Distributed Inference Setup](../mesh-inference/setup.md)

### Fleet Management

Configure a "chief" node to manage other nodes:

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "fleet": {
        "chief": true,
        "allow_remote_update": true,
        "allow_update_from": [
          "<paired peer_id>"
        ]
      }
    }
  }
}
```

Details: [Fleet Management](../features/fleet-admin.md)

### Generation Distribution (SD / ComfyUI Job Delegation)

Automatically distribute generation jobs to GPU-equipped nodes. Available via configuration file backend registration or mDNS auto-discovery.  
If Node B is running SD WebUI / ComfyUI, it becomes available immediately after configuration.

---

## Network Requirements

| Port / Protocol | Purpose | Required |
|---|---|---|
| UDP 5353 | mDNS (node discovery) | Same L2 LAN only |
| UDP 19850 | LAN Cowork discovery | Same L2 LAN only |
| TCP 5000 (default) | API, pairing, inference | Between peers |

- mDNS does not work across routers or VPNs (use fixed IP or `.local` hostname)
- Ensure UDP 5353 and TCP 5000 are open on the LAN in your firewall

---

## Documentation Index

| Document | Content |
|---|---|
| [Peer PIN Authentication](peer-auth.md) | Pairing flow, token management, security configuration |
| [Distributed Inference Setup](../mesh-inference/setup.md) | Steps to parallelize inference across multiple nodes |
| [Distributed Inference Matrix](../mesh-inference/toggle.md) | Enable/disable per-peer and per-type via WebUI |
| [Distributed Inference Architecture](../mesh-inference/overview.md) | Internal design, work stealing, persistence |
| [Fleet Management](../features/fleet-admin.md) | Centralized management of remote logs and version updates |
| [mDNS Peer API](../api/mdns-peers.md) | Details of `/api/mdns/*` endpoints |

---

## Security

- mDNS has no authentication. **Use only on home LANs or trusted networks**
- On public Wi-Fi or shared LANs, disable with `"mdns": {"enabled": false}`
- Peer communication is protected by Bearer tokens from PIN pairing (stored as scrypt hash)
- `ip_check_mode: strict` allows only the IP from which the token was issued (default)
