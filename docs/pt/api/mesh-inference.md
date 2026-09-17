# API: /api/mesh-inference

**Versão**: v4.67.0 e posterior

API para recuperar e atualizar o estado da matriz de inferência distribuída. Todos os endpoints retornam o formato comum `{"ok": bool, "error"?, "code"?, ...}` de `core/infra_core/api_errors.py`.

## `GET /api/mesh-inference/state`

Retorna uma lista de todos os pares e seu estado desabilitado atual.

**Resposta**:
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

Alterna a flag desabilitada para um único par (peer, inference_type).

**Requisição**:
```json
{ "peer_id": "pi5-kitchen-abc", "inference_type": "clip", "disabled": true }
```

**Erros**:
- 400 `invalid_peer_id` -- peer_id não corresponde a `^[A-Za-z0-9_\-.:]{1,64}$`
- 400 `unknown_inference_type` -- não é um de `tagger`/`clip`/`yolo`/`whisper`
- 400 `type_not_advertised` -- o par não fornece o tipo especificado
- 404 `unknown_peer` -- peer_id não existe em `PeerRegistry`

Desabilitar um par offline é permitido (a configuração é aplicada quando ele se reconecta).

## `POST /api/mesh-inference/bulk`

Operações em lote.

**Requisição**:
```json
{ "action": "disable_all_remote", "inference_type": "clip" }
{ "action": "enable_all", "inference_type": "tagger" }
{ "action": "local_only" }
```

**Erros**:
- 409 `local_peer_has_no_effective_types` -- `local_only` quando o par local não tem tipos de inferência efetivos
- 400 `unknown_action` -- não é uma das três ações acima
- 400 `unknown_inference_type` -- `disable_all_remote` / `enable_all` sem um tipo especificado

## `POST /api/mesh-inference/refresh`

Re-busca a lista de pares e a retorna. A forma de resposta é a mesma que `GET /state`.

## Ferramentas MCP

- `mesh_inference_state` -- Wrapper para `GET /state`
- `mesh_inference_toggle` -- Wrapper para `POST /toggle`. **Desabilitar o par local é proibido** (apenas permitido via WebUI)
- `mesh_inference_bulk` -- Wrapper para `POST /bulk`

## Persistência

Em cada alteração, uma escrita atômica é feita para `data/mesh_inference_state.json`:

```json
{
  "version": 1,
  "disabled": {
    "pi5-kitchen-abc": ["clip"]
  }
}
```

JSON corrompido ou incompatibilidades de `version` caem de volta para um estado vazio.
