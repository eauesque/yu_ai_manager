# API: /api/mesh-inference

**Версия**: v4.67.0 и позже

API для получения и обновления состояния матрицы распределенного вывода. Все конечные точки возвращают общий формат `{"ok": bool, "error"?, "code"?, ...}` из `core/infra_core/api_errors.py`.

## `GET /api/mesh-inference/state`

Возвращает список всех пиров и их текущее отключенное состояние.

**Ответ**:
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

Переключает отключенный флаг для одной пары (peer, inference_type).

**Запрос**:
```json
{ "peer_id": "pi5-kitchen-abc", "inference_type": "clip", "disabled": true }
```

**Ошибки**:
- 400 `invalid_peer_id` -- peer_id не совпадает с `^[A-Za-z0-9_\-.:]{1,64}$`
- 400 `unknown_inference_type` -- не один из `tagger`/`clip`/`yolo`/`whisper`
- 400 `type_not_advertised` -- пир не предоставляет указанный тип
- 404 `unknown_peer` -- peer_id не существует в `PeerRegistry`

Отключение оффлайн пира разрешено (параметр применяется при повторном подключении).

## `POST /api/mesh-inference/bulk`

Массовые операции.

**Запрос**:
```json
{ "action": "disable_all_remote", "inference_type": "clip" }
{ "action": "enable_all", "inference_type": "tagger" }
{ "action": "local_only" }
```

**Ошибки**:
- 409 `local_peer_has_no_effective_types` -- `local_only` когда локальный пир не имеет эффективных типов вывода
- 400 `unknown_action` -- не один из трех действий выше
- 400 `unknown_inference_type` -- `disable_all_remote` / `enable_all` без указанного типа

## `POST /api/mesh-inference/refresh`

Повторно получает список пиров и возвращает его. Форма ответа совпадает с `GET /state`.

## MCP инструменты

- `mesh_inference_state` -- Обертка для `GET /state`
- `mesh_inference_toggle` -- Обертка для `POST /toggle`. **Отключение локального пира запрещено** (разрешено только через WebUI)
- `mesh_inference_bulk` -- Обертка для `POST /bulk`

## Сохранение

При каждом переключении выполняется атомарная запись в `data/mesh_inference_state.json`:

```json
{
  "version": 1,
  "disabled": {
    "pi5-kitchen-abc": ["clip"]
  }
}
```

Поврежденный JSON или несовпадения `version` возвращаются к пустому состоянию.
