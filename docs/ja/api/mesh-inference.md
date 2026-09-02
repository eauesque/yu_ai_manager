# API: /api/mesh-inference

**バージョン**: v4.67.0 以降

分散推論マトリクスの状態取得・更新 API。全エンドポイントは `core/infra_core/api_errors.py` の共通形式 `{"ok": bool, "error"?, "code"?, ...}` を返します。

## `GET /api/mesh-inference/state`

全ピアの一覧と現在の disabled 状態を返します。

**レスポンス**:
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

単一の (peer, inference_type) の disabled フラグを切替。

**リクエスト**:
```json
{ "peer_id": "pi5-kitchen-abc", "inference_type": "clip", "disabled": true }
```

**エラー**:
- 400 `invalid_peer_id` — peer_id が `^[A-Za-z0-9_\-.:]{1,64}$` にマッチしない
- 400 `unknown_inference_type` — `tagger`/`clip`/`yolo`/`whisper` 以外
- 400 `type_not_advertised` — 該当ピアがそのタイプを提供していない
- 404 `unknown_peer` — `PeerRegistry` に存在しない peer_id

オフラインのピアに対する disable は許可されます（復帰時に適用）。

## `POST /api/mesh-inference/bulk`

一括操作。

**リクエスト**:
```json
{ "action": "disable_all_remote", "inference_type": "clip" }
{ "action": "enable_all", "inference_type": "tagger" }
{ "action": "local_only" }
```

**エラー**:
- 409 `local_peer_has_no_effective_types` — `local_only` で、ローカルに有効な推論タイプが 1 つもない
- 400 `unknown_action` — 上記 3 つ以外
- 400 `unknown_inference_type` — `disable_all_remote` / `enable_all` で type が指定されていない

## `POST /api/mesh-inference/refresh`

ピアリストを再取得して返す。レスポンス形状は `GET /state` と同じ。

## MCP ツール

- `mesh_inference_state` — `GET /state` ラッパー
- `mesh_inference_toggle` — `POST /toggle` ラッパー。**ただしローカルピアの disable は禁止**（WebUI 経由のみ可）
- `mesh_inference_bulk` — `POST /bulk` ラッパー

## 永続化

トグルのたびに `data/mesh_inference_state.json` にアトミック書き込み:

```json
{
  "version": 1,
  "disabled": {
    "pi5-kitchen-abc": ["clip"]
  }
}
```

破損 JSON や `version` 不一致は空 state にフォールバックします。
