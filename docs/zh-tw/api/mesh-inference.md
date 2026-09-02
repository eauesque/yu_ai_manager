# API：/api/mesh-inference

**版本**：v4.67.0 以後

分散推論矩陣的狀態取得與更新 API。所有端點回傳 `core/infra_core/api_errors.py` 的共通格式 `{"ok": bool, "error"?, "code"?, ...}`。

## `GET /api/mesh-inference/state`

回傳所有 peer 的列表與目前的 disabled 狀態。

**回應**：
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

切換單一 (peer, inference_type) 的 disabled 旗標。

**請求**：
```json
{ "peer_id": "pi5-kitchen-abc", "inference_type": "clip", "disabled": true }
```

**錯誤**：
- 400 `invalid_peer_id` — peer_id 不符合 `^[A-Za-z0-9_\-.:]{1,64}$`
- 400 `unknown_inference_type` — 非 `tagger`/`clip`/`yolo`/`whisper`
- 400 `type_not_advertised` — 該 peer 未提供該類型
- 404 `unknown_peer` — `PeerRegistry` 中不存在該 peer_id

允許對離線的 peer 進行 disable（恢復時套用）。

## `POST /api/mesh-inference/bulk`

批次操作。

**請求**：
```json
{ "action": "disable_all_remote", "inference_type": "clip" }
{ "action": "enable_all", "inference_type": "tagger" }
{ "action": "local_only" }
```

**錯誤**：
- 409 `local_peer_has_no_effective_types` — `local_only` 時本機無有效的推論類型
- 400 `unknown_action` — 非上述 3 種
- 400 `unknown_inference_type` — `disable_all_remote` / `enable_all` 時未指定 type

## `POST /api/mesh-inference/refresh`

重新取得 peer 列表並回傳。回應格式與 `GET /state` 相同。

## MCP 工具

- `mesh_inference_state` — `GET /state` 包裝器
- `mesh_inference_toggle` — `POST /toggle` 包裝器。**但禁止停用本機 peer**（僅可透過 WebUI）
- `mesh_inference_bulk` — `POST /bulk` 包裝器

## 永久化

每次切換時以原子寫入方式儲存至 `data/mesh_inference_state.json`：

```json
{
  "version": 1,
  "disabled": {
    "pi5-kitchen-abc": ["clip"]
  }
}
```

損毀的 JSON 或 `version` 不符時會回退為空狀態。
