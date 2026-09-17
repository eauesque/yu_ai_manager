# Mesh Inference Matrix

**Version**: v4.67.0 and later

## Overview

On the `/mesh-inference` page, you can enable or disable each inference type on a per-peer basis for peers participating in mesh inference. The target inference types are tagger, clip, yolo, and whisper.

This allows you to dedicate the Pi5's Hailo NPU to tagger only, or have a GPU host handle clip, and so on -- all without touching the config.

## Usage

1. Click "Mesh Inference" in the navigation bar
2. Click each cell in the matrix table to toggle enable/disable
   - Checked = enabled (use that inference type on that peer)
   - Unchecked = disabled (skip that peer)
   - Dash = that peer does not provide the inference type (not toggleable)
3. The "Local Only Mode" button disables all remote peers at once
4. State is automatically persisted to `data/mesh_inference_state.json`

## Behavior

- Settings are retained for offline peers (automatically applied when they reconnect)
- "Local Only Mode" can only be pressed when the local node has at least one enabled type
- Starting a tagger batch when tagger is disabled on all peers results in an immediate `no_enabled_peers` error
- Disabled state is preserved even when peers temporarily leave and rejoin via mDNS re-discovery

## Relationship with Existing YOLO Distributed Inference Checkbox

The "Distributed Inference" checkbox on the YOLO detection page is retained for backward compatibility. It interacts with the matrix as follows:

| yoloDistributed | Matrix yolo column | Actual behavior |
|---|---|---|
| ON | All peers enabled | Distributed across all peers as before |
| ON | Some disabled | Disabled peers are skipped |
| OFF | Ignored | Local only (router bypassed) |

## Related

- API reference: [api/mesh-inference.md](../api/mesh-inference.md)
- LLM Router (separate layer): [../llm-router/](../llm-router/)
