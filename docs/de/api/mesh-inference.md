# API: /api/mesh-inference

**Version**: v4.67.0 und später

API zum Abrufen und Aktualisieren des verteilten Inferenz-Matrix-Status. Alle Endpunkte geben das gemeinsame Format `{"ok": bool, "error"?, "code"?, ...}` aus `core/infra_core/api_errors.py` zurück.

## `GET /api/mesh-inference/state`

Gibt eine Liste aller Peers und ihren aktuellen deaktivierten Status zurück.

**Antwort**:
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

Wechseln Sie das deaktivierte Flag für ein einzelnes (peer, inference_type)-Paar.

**Anfrage**:
```json
{ "peer_id": "pi5-kitchen-abc", "inference_type": "clip", "disabled": true }
```

**Fehler**:
- 400 `invalid_peer_id` -- peer_id stimmt nicht mit `^[A-Za-z0-9_\-.:]{1,64}$` überein
- 400 `unknown_inference_type` -- nicht einer von `tagger`/`clip`/`yolo`/`whisper`
- 400 `type_not_advertised` -- der Peer stellt den angegebenen Typ nicht bereit
- 404 `unknown_peer` -- peer_id existiert nicht in `PeerRegistry`

Das Deaktivieren eines Offline-Peers ist zulässig (die Einstellung wird angewendet, wenn er sich wieder verbindet).

## `POST /api/mesh-inference/bulk`

Bulk-Operationen.

**Anfrage**:
```json
{ "action": "disable_all_remote", "inference_type": "clip" }
{ "action": "enable_all", "inference_type": "tagger" }
{ "action": "local_only" }
```

**Fehler**:
- 409 `local_peer_has_no_effective_types` -- `local_only`, wenn der lokale Peer keine effektiven Inferenztypen hat
- 400 `unknown_action` -- nicht einer der drei obigen Aktionen
- 400 `unknown_inference_type` -- `disable_all_remote` / `enable_all` ohne angegebenen Typ

## `POST /api/mesh-inference/refresh`

Ruft die Peer-Liste erneut ab und gibt sie zurück. Das Antwortformat ist das gleiche wie bei `GET /state`.

## MCP-Tools

- `mesh_inference_state` -- Wrapper für `GET /state`
- `mesh_inference_toggle` -- Wrapper für `POST /toggle`. **Das Deaktivieren des lokalen Peers ist verboten** (nur über WebUI erlaubt)
- `mesh_inference_bulk` -- Wrapper für `POST /bulk`

## Persistierung

Bei jedem Toggle wird ein atomares Schreiben zu `data/mesh_inference_state.json` durchgeführt:

```json
{
  "version": 1,
  "disabled": {
    "pi5-kitchen-abc": ["clip"]
  }
}
```

Beschädigte JSON oder `version`-Nichtübereinstimmungen fallen auf einen leeren Status zurück.
