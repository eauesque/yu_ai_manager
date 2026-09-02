# API : /api/mesh-inference

**Version** : v4.67.0 et ultérieures

API pour récupérer et mettre à jour l'état de la matrice d'inférence distribuée. Tous les points d'accès retournent le format commun `{"ok": bool, "error"?, "code"?, ...}` de `core/infra_core/api_errors.py`.

## `GET /api/mesh-inference/state`

Retourne une liste de tous les pairs et leur état désactivé actuel.

**Réponse** :
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

Bascule le drapeau désactivé pour une seule paire (peer, inference_type).

**Requête** :
```json
{ "peer_id": "pi5-kitchen-abc", "inference_type": "clip", "disabled": true }
```

**Erreurs** :
- 400 `invalid_peer_id` -- peer_id ne correspond pas à `^[A-Za-z0-9_\-.:]{1,64}$`
- 400 `unknown_inference_type` -- pas l'un de `tagger`/`clip`/`yolo`/`whisper`
- 400 `type_not_advertised` -- le pair ne fournit pas le type spécifié
- 404 `unknown_peer` -- peer_id n'existe pas dans `PeerRegistry`

La désactivation d'un pair hors ligne est autorisée (le paramètre est appliqué lors de la reconnexion).

## `POST /api/mesh-inference/bulk`

Opérations en masse.

**Requête** :
```json
{ "action": "disable_all_remote", "inference_type": "clip" }
{ "action": "enable_all", "inference_type": "tagger" }
{ "action": "local_only" }
```

**Erreurs** :
- 409 `local_peer_has_no_effective_types` -- `local_only` quand le pair local n'a pas de types d'inférence efficaces
- 400 `unknown_action` -- pas l'une des trois actions ci-dessus
- 400 `unknown_inference_type` -- `disable_all_remote` / `enable_all` sans type spécifié

## `POST /api/mesh-inference/refresh`

Re-récupère la liste des pairs et la retourne. La forme de réponse est la même que `GET /state`.

## Outils MCP

- `mesh_inference_state` -- Wrapper pour `GET /state`
- `mesh_inference_toggle` -- Wrapper pour `POST /toggle`. **La désactivation du pair local est interdite** (uniquement autorisée via WebUI)
- `mesh_inference_bulk` -- Wrapper pour `POST /bulk`

## Persistance

À chaque basculement, une écriture atomique est effectuée vers `data/mesh_inference_state.json` :

```json
{
  "version": 1,
  "disabled": {
    "pi5-kitchen-abc": ["clip"]
  }
}
```

JSON corrompu ou non-correspondance `version` revient à un état vide.
