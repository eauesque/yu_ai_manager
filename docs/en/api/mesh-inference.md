# API: /api/mesh-inference

**Version**: v4.67.0 and later

API for retrieving and updating the distributed inference matrix state. All endpoints return the common format `{"ok": bool, "error"?, "code"?, ...}` from `core/infra_core/api_errors.py`.

## `GET /api/mesh-inference/state`

Returns a list of all peers and their current disabled state.

**Response**:
```json
{
  "ok": true,
  "peers": [
    {
      "peer_id": "local",
      "name": "local",
      "status": "online",
      "is_local": true,
      "inference_types": ["tagger", "clip", "yolo"],
      "device_info": "onnx-cuda",
      "disabled_types": []
    },
    {
      "peer_id": "pi5-kitchen-abc",
      "name": "pi5-kitchen",
      "status": "online",
      "is_local": false,
      "inference_types": ["tagger", "clip", "yolo"],
      "device_info": "hailo-10h",
      "disabled_types": ["clip"]
    }
  ]
}
```

## `POST /api/mesh-inference/toggle`

Toggles the disabled flag for a single (peer, inference_type) pair.

**Request**:
```json
{ "peer_id": "pi5-kitchen-abc", "inference_type": "clip", "disabled": true }
```

**Errors**:
- 400 `invalid_peer_id` -- peer_id does not match `^[A-Za-z0-9_\-.:]{1,64}$`
- 400 `unknown_inference_type` -- not one of `tagger`/`clip`/`yolo`/`whisper`
- 400 `type_not_advertised` -- the peer does not provide the specified type
- 404 `unknown_peer` -- peer_id does not exist in `PeerRegistry`

Disabling an offline peer is permitted (the setting is applied when it reconnects).

## `POST /api/mesh-inference/bulk`

Bulk operations.

**Request**:
```json
{ "action": "disable_all_remote", "inference_type": "clip" }
{ "action": "enable_all", "inference_type": "tagger" }
{ "action": "local_only" }
```

**Errors**:
- 409 `local_peer_has_no_effective_types` -- `local_only` when the local peer has no effective inference types
- 400 `unknown_action` -- not one of the three actions above
- 400 `unknown_inference_type` -- `disable_all_remote` / `enable_all` without a specified type

## `POST /api/mesh-inference/refresh`

Re-fetches the peer list and returns it. The response shape is the same as `GET /state`.

## MCP Tools

- `mesh_inference_state` -- Wrapper for `GET /state`
- `mesh_inference_toggle` -- Wrapper for `POST /toggle`. **Disabling the local peer is prohibited** (only allowed via WebUI)
- `mesh_inference_bulk` -- Wrapper for `POST /bulk`

## Persistence

On each toggle, an atomic write is made to `data/mesh_inference_state.json`:

```json
{
  "version": 1,
  "disabled": {
    "pi5-kitchen-abc": ["clip"]
  }
}
```

Corrupted JSON or `version` mismatches fall back to an empty state.
