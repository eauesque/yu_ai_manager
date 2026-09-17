# API: /api/mesh-inference

**版本**: v4.67.0 及以上

分布式推理矩阵的状态获取与更新 API。所有端点返回 `core/infra_core/api_errors.py` 的通用格式 `{"ok": bool, "error"?, "code"?, ...}`。

## `GET /api/mesh-inference/state`

返回所有节点的列表及当前的 disabled 状态。

**响应**:
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

切换单个 (peer, inference_type) 的 disabled 标志。

**请求**:
```json
{ "peer_id": "pi5-kitchen-abc", "inference_type": "clip", "disabled": true }
```

**错误**:
- 400 `invalid_peer_id` — peer_id 不匹配 `^[A-Za-z0-9_\-.:]{1,64}$`
- 400 `unknown_inference_type` — 不是 `tagger`/`clip`/`yolo`/`whisper`
- 400 `type_not_advertised` — 该节点未提供该类型
- 404 `unknown_peer` — `PeerRegistry` 中不存在的 peer_id

允许对离线节点执行 disable（恢复在线时应用）。

## `POST /api/mesh-inference/bulk`

批量操作。

**请求**:
```json
{ "action": "disable_all_remote", "inference_type": "clip" }
{ "action": "enable_all", "inference_type": "tagger" }
{ "action": "local_only" }
```

**错误**:
- 409 `local_peer_has_no_effective_types` — `local_only` 时本地没有有效的推理类型
- 400 `unknown_action` — 上述 3 种以外的 action
- 400 `unknown_inference_type` — `disable_all_remote` / `enable_all` 时未指定 type

## `POST /api/mesh-inference/refresh`

重新获取节点列表并返回。响应格式与 `GET /state` 相同。

## MCP 工具

- `mesh_inference_state` — `GET /state` 的包装
- `mesh_inference_toggle` — `POST /toggle` 的包装。**但禁止 disable 本地节点**（仅限通过 WebUI 操作）
- `mesh_inference_bulk` — `POST /bulk` 的包装

## 持久化

每次切换时原子写入 `data/mesh_inference_state.json`:

```json
{
  "version": 1,
  "disabled": {
    "pi5-kitchen-abc": ["clip"]
  }
}
```

JSON 损坏或 `version` 不匹配时回退到空状态。
