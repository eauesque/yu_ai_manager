# API: /api/mesh-inference

**Versión**: v4.67.0 y posteriores

API para recuperar y actualizar el estado de la matriz de inferencia distribuida. Todos los endpoints devuelven el formato común `{"ok": bool, "error"?, "code"?, ...}` de `core/infra_core/api_errors.py`.

## `GET /api/mesh-inference/state`

Devuelve una lista de todos los pares y su estado deshabilitado actual.

**Respuesta**:
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

Alterna la bandera deshabilitada para un único par (peer, inference_type).

**Solicitud**:
```json
{ "peer_id": "pi5-kitchen-abc", "inference_type": "clip", "disabled": true }
```

**Errores**:
- 400 `invalid_peer_id` -- peer_id no coincide con `^[A-Za-z0-9_\-.:]{1,64}$`
- 400 `unknown_inference_type` -- no es uno de `tagger`/`clip`/`yolo`/`whisper`
- 400 `type_not_advertised` -- el par no proporciona el tipo especificado
- 404 `unknown_peer` -- peer_id no existe en `PeerRegistry`

Deshabilitar un par sin conexión está permitido (la configuración se aplica cuando se reconecta).

## `POST /api/mesh-inference/bulk`

Operaciones por lotes.

**Solicitud**:
```json
{ "action": "disable_all_remote", "inference_type": "clip" }
{ "action": "enable_all", "inference_type": "tagger" }
{ "action": "local_only" }
```

**Errores**:
- 409 `local_peer_has_no_effective_types` -- `local_only` cuando el par local no tiene tipos de inferencia efectivos
- 400 `unknown_action` -- no es una de las tres acciones anteriores
- 400 `unknown_inference_type` -- `disable_all_remote` / `enable_all` sin un tipo especificado

## `POST /api/mesh-inference/refresh`

Vuelve a obtener la lista de pares y la devuelve. La forma de respuesta es la misma que `GET /state`.

## Herramientas MCP

- `mesh_inference_state` -- Envoltorio para `GET /state`
- `mesh_inference_toggle` -- Envoltorio para `POST /toggle`. **Se prohíbe deshabilitar el par local** (solo se permite a través de WebUI)
- `mesh_inference_bulk` -- Envoltorio para `POST /bulk`

## Persistencia

En cada alternancia, se realiza una escritura atómica a `data/mesh_inference_state.json`:

```json
{
  "version": 1,
  "disabled": {
    "pi5-kitchen-abc": ["clip"]
  }
}
```

JSON corrupto o desajustes de `version` vuelven a un estado vacío.
