# API: /api/mesh-inference

**버전**: v4.67.0 이후

분산 추론 매트릭스의 상태 취득 및 갱신 API. 모든 엔드포인트는 `core/infra_core/api_errors.py`의 공통 형식 `{"ok": bool, "error"?, "code"?, ...}`을 반환합니다.

## `GET /api/mesh-inference/state`

전체 피어의 목록과 현재의 disabled 상태를 반환합니다.

**응답**:
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

단일 (peer, inference_type)의 disabled 플래그를 전환합니다.

**요청**:
```json
{ "peer_id": "pi5-kitchen-abc", "inference_type": "clip", "disabled": true }
```

**에러**:
- 400 `invalid_peer_id` — peer_id가 `^[A-Za-z0-9_\-.:]{1,64}$`에 매치되지 않음
- 400 `unknown_inference_type` — `tagger`/`clip`/`yolo`/`whisper` 이외
- 400 `type_not_advertised` — 해당 피어가 그 타입을 제공하지 않음
- 404 `unknown_peer` — `PeerRegistry`에 존재하지 않는 peer_id

오프라인 피어에 대한 disable은 허용됩니다 (복귀 시 적용).

## `POST /api/mesh-inference/bulk`

일괄 조작.

**요청**:
```json
{ "action": "disable_all_remote", "inference_type": "clip" }
{ "action": "enable_all", "inference_type": "tagger" }
{ "action": "local_only" }
```

**에러**:
- 409 `local_peer_has_no_effective_types` — `local_only`에서 로컬에 유효한 추론 타입이 하나도 없음
- 400 `unknown_action` — 위 3가지 이외
- 400 `unknown_inference_type` — `disable_all_remote` / `enable_all`에서 type이 지정되지 않음

## `POST /api/mesh-inference/refresh`

피어 목록을 재취득하여 반환합니다. 응답 형태는 `GET /state`와 동일합니다.

## MCP 도구

- `mesh_inference_state` — `GET /state` 래퍼
- `mesh_inference_toggle` — `POST /toggle` 래퍼. **단, 로컬 피어의 disable은 금지** (WebUI 경유만 가능)
- `mesh_inference_bulk` — `POST /bulk` 래퍼

## 영구화

토글할 때마다 `data/mesh_inference_state.json`에 아토믹 기록:

```json
{
  "version": 1,
  "disabled": {
    "pi5-kitchen-abc": ["clip"]
  }
}
```

손상된 JSON이나 `version` 불일치는 빈 state로 폴백됩니다.
