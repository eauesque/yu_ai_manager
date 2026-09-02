# Distributed Inference Setup Guide

> Target version: v4.67.0 and later

## What is Distributed Inference

A feature where multiple yu_ai_manager nodes collaborate to **parallelize and distribute** inference processing such as tagging, CLIP, YOLO, and speech recognition. You can share large file scans across multiple machines or delegate tagging to a Pi5 with Hailo NPU.

```
┌──────────────┐   Image Batch   ┌──────────────┐
│    Local     │ ──────────────► │  Pi5 (Hailo) │  tagger × 200 images
│   (Scan)     │ ──────────────► │  GPU Machine │  tagger × 300 images
│              │ ──────────────► │    Local     │  tagger × 100 images
└──────────────┘   Work          └──────────────┘
                  Stealing
```

---

## Prerequisites

The following conditions must be met on each node:

1. yu_ai_manager is running
2. **LAN Cowork extension is enabled** (`"extensions": {"builtin-lan-cowork": {"enabled": true}}`)
3. Nodes are **paired with each other** ([Peer Authentication Guide](../lan-cowork/peer-auth.md))
4. Inference engines to be used are set up on each node (ONNX / Hailo / Whisper, etc.)

---

## Setup Steps

### Step 1: Enable LAN Cowork on Each Node

In `config.json` on all nodes:

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "enabled": true
    }
  }
}
```

After restart, nodes will auto-discover each other via mDNS.

### Step 2: Complete Pairing

Perform pairing between all node pairs (bidirectional).
Detail: [Peer PIN Authentication and Token Pairing](../lan-cowork/peer-auth.md)

### Step 3: Verify the Distributed Inference Matrix

Open `/mesh-inference` on any node.

Paired nodes appear as rows, inference types appear as columns:

| Node | tagger | clip | yolo | whisper |
|---|---|---|---|---|
| Local | ☑ Enabled | ☑ Enabled | ☑ Enabled | ☑ Enabled |
| pi5-hailo | ☑ Enabled | ☑ Enabled | — Not Available | — Not Available |
| gpu-win | ☑ Enabled | ☑ Enabled | ☑ Enabled | ☑ Enabled |

- **☑ Enabled**: Use this node for inference
- **☐ Disabled**: Skip (can be toggled manually)
- **—**: This node does not have the target inference engine (cannot be operated)

### Step 4: Verify Operation

Run a tagging batch and confirm in logs that multiple nodes are being used:

```
[mesh-inference] dispatching tagger: 600 items to 3 peers
[mesh-inference] pi5-hailo: processed 200, errors 0
[mesh-inference] gpu-win:   processed 300, errors 0
[mesh-inference] local:     processed 100, errors 0
```

---

## Inference Type Requirements

| Type | Required Engine | Description |
|---|---|---|
| `tagger` | ONNX (WD14, etc.) or Hailo NPU | Danbooru-style tagging for images |
| `clip` | ONNX CLIP or Hailo | Semantic embedding vectors for images (for semantic search) |
| `yolo` | ONNX YOLO | Object detection in images |
| `whisper` | faster-whisper or remote | Speech-to-text transcription for audio/video |

Nodes without an engine configured will show "—" for that type and will not be routed for that type.

---

## Role Design Examples

### Example 1: Dedicate Pi5 + Hailo NPU for Tagging

Allocate Pi5 exclusively for tagging to reduce load on other nodes.

Matrix configuration:
- Pi5: tagger ☑, others ☐
- Local: clip ☑, yolo ☑, whisper ☑, tagger ☐ (delegate to Pi5)

### Example 2: Fast Bulk Scan

Enable tagger on both GPU machine and local machine, automatically sharing files via work stealing. No manual splitting needed.

### Example 3: Local-Only Mode (Temporary)

Click the "Local-Only Mode" button in `/mesh-inference` to disable all remote peers at once. Useful when network is disconnected.

---

## Troubleshooting

### Peer Does Not Appear in Matrix

1. Verify peer is recognized with `/api/lan/peers`
2. Confirm pairing is complete ([peer-auth.md](../lan-cowork/peer-auth.md))
3. Verify LAN Cowork is enabled on the remote node

### Routing to Specific Node Is Not Working

- Verify the target type for that node shows ☑ in the matrix
- Check that `/api/lan/peers` response shows `status: "online"` for that node
- Verify the remote node's heartbeat is being received (search logs for `heartbeat`)

### Everything Is Processed Locally

If all remote peers are offline or disabled, automatic local fallback occurs.
This is normal operation (not an error).

### `no_enabled_peers` Error

That type is disabled on all nodes.
Enable at least 1 node for that type in the matrix.

---

## Related Documentation

- [Distributed Inference Architecture](overview.md) — Work stealing and DisableAwareStrategy internal design
- [Distributed Inference Matrix](toggle.md) — WebUI operation details
- [LAN Cowork Overview](../lan-cowork/README.md) — LAN Cowork overall configuration
- [Peer PIN Authentication](../lan-cowork/peer-auth.md) — Pairing procedure
