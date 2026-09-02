# API: /api/mesh-inference

**Versione**: v4.67.0 e successive

API per il recupero e l'aggiornamento dello stato della matrice di inferenza distribuita. Tutti gli endpoint restituiscono il formato comune `{"ok": bool, "error"?, "code"?, ...}` da `core/infra_core/api_errors.py`.

## `GET /api/mesh-inference/state`

Restituisce un elenco di tutti i peer e il loro stato disabilitato attuale.

**Risposta**:
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

Attiva/disattiva il flag disabilitato per una singola coppia (peer, inference_type).

**Richiesta**:
```json
{ "peer_id": "pi5-kitchen-abc", "inference_type": "clip", "disabled": true }
```

**Errori**:
- 400 `invalid_peer_id` -- peer_id non corrisponde a `^[A-Za-z0-9_\-.:]{1,64}$`
- 400 `unknown_inference_type` -- non uno di `tagger`/`clip`/`yolo`/`whisper`
- 400 `type_not_advertised` -- il peer non fornisce il tipo specificato
- 404 `unknown_peer` -- peer_id non esiste in `PeerRegistry`

La disabilitazione di un peer offline è consentita (l'impostazione viene applicata quando si riconnette).

## `POST /api/mesh-inference/bulk`

Operazioni in massa.

**Richiesta**:
```json
{ "action": "disable_all_remote", "inference_type": "clip" }
{ "action": "enable_all", "inference_type": "tagger" }
{ "action": "local_only" }
```

**Errori**:
- 409 `local_peer_has_no_effective_types` -- `local_only` quando il peer locale non ha tipi di inferenza effettivi
- 400 `unknown_action` -- non uno dei tre azioni di cui sopra
- 400 `unknown_inference_type` -- `disable_all_remote` / `enable_all` senza un tipo specificato

## `POST /api/mesh-inference/refresh`

Re-fetch dell'elenco peer e lo restituisce. La forma della risposta è la stessa di `GET /state`.

## Strumenti MCP

- `mesh_inference_state` -- Wrapper per `GET /state`
- `mesh_inference_toggle` -- Wrapper per `POST /toggle`. **La disabilitazione del peer locale è proibita** (consentita solo tramite WebUI)
- `mesh_inference_bulk` -- Wrapper per `POST /bulk`

## Persistenza

Ad ogni attivazione/disattivazione, viene eseguita una scrittura atomica in `data/mesh_inference_state.json`:

```json
{
  "version": 1,
  "disabled": {
    "pi5-kitchen-abc": ["clip"]
  }
}
```

JSON corrotto o mancate corrispondenze di `version` ricadono in uno stato vuoto.
