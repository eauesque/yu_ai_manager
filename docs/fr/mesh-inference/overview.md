# Architecture d'Inférence en Maille

> Version cible : v4.67.0 et suivantes

## Vue d'ensemble

Le système d'inférence en maille est un mécanisme par lequel plusieurs nœuds yu_ai_manager sur le LAN coopèrent pour traiter de manière distribuée des tâches d'inférence (tagger / clip / yolo / whisper). En combinant la découverte automatique mDNS, le vol de travail (work-stealing) via `asyncio.Queue`, et un filtre de désactivation par nœud, il passe à l'échelle horizontale sans configuration.

---

## Architecture Globale

```
┌─────────────────────────────────────────────────┐
│                 CoworkManager                   │
│  Crée InferenceRouter au démarrage et           │
│  l'enregistre via core.mesh_inference.set_router() │
└────────────────────┬────────────────────────────┘
                     │
          ┌──────────▼──────────┐
          │   InferenceRouter   │  extensions/builtin_lan_cowork/
          │                     │  core_impl/inference/router.py
          │  _local_peer        │
          │  _registry ─────────┼──► PeerRegistry (liste des pairs LAN)
          │  _strategy ─────────┼──► DisableAwareStrategy
          └──────────┬──────────┘
                     │ dispatch_inference()
          ┌──────────▼──────────┐
          │   asyncio.Queue     │  file d'attente work-stealing
          │   item, item, ...   │
          └──┬───────────┬──────┘
             │           │
       ┌─────▼──┐   ┌────▼────┐
       │ peer A │   │ peer B  │   (workers concurrents)
       │(local) │   │(remote) │
       └────────┘   └─────────┘
```

### Responsabilités des Composants

| Composant | Emplacement | Responsabilité |
|---|---|---|
| `core.mesh_inference` | `core/mesh_inference/__init__.py` | Façade : get_router / set_router |
| `InferenceRouter` | `extensions/builtin_lan_cowork/…/router.py` | Distribution par lot, work-stealing |
| `PeerRegistry` | `extensions/builtin_lan_cowork/…/registry.py` | Gestion des pairs, jugement en ligne |
| `DisableAwareStrategy` | `core/mesh_inference/strategy.py` | Filtre de désactivation per-peer-per-type |
| `InferenceState` | `extensions/builtin_lan_cowork/…/state.py` | Référence au moteur local |
| `dispatch_sync` | `core/mesh_inference/dispatch_sync.py` | Pont async→thread |
| `persistence` | `core/mesh_inference/persistence.py` | Persistance JSON |

---

## Découverte Automatique des Pairs (mDNS Phase B)

Le service `_yu-ai._tcp.local.` est annoncé sur le LAN, et la navigation de ce même service permet la découverte mutuelle.

```
node A                               node B
  │  ── mDNS advertise ──►           │
  │  ◄── mDNS browse ────            │
  │                                  │
  │  ── GET /api/mdns/identity ──►   │
  │  ◄── {node_id, capabilities} ─── │
  │                                  │
  │  Enregistrement dans PeerRegistry │
```

Détails du flux de découverte :
1. `LlmRouterMdnsBridge` reçoit les événements mDNS
2. Vérification HTTP `/api/mdns/identity` pour confirmer que le pair est bien yu_ai_manager
3. Après validation, ajout du pair à `PeerRegistry`
4. La liste de types retournée par `InferenceState.get_inference_types()` est reflétée dans `PeerInfo.inference_types`

---

## Types d'Inférence et Backends

La chaîne retournée par `InferenceState.get_inference_types()` est définie dans `PeerInfo.inference_types` et sert de critère de routage.

| Type d'inférence | Backend | Usage |
|---|---|---|
| `tagger` | ONNX (WD14, etc.) / Hailo NPU | Étiquetage d'image |
| `clip` | ONNX / Hailo / distant | Vecteur d'embedding d'image |
| `yolo` | ONNX / Hailo | Détection d'objets |
| `whisper` | faster-whisper / distant | Transcription vocale |
| `hailo` | vdevice Hailo-10H | Accès direct au périphérique Hailo |
| `llm` | OpenAI-compat / Ollama | Inférence LLM |

Les types dont le moteur est `None` ne sont pas inclus dans la liste de `get_inference_types()`, donc pas routés vers ce pair.

---

## Algorithme de Work-Stealing

```python
# router.py (résumé)
queue: asyncio.Queue = asyncio.Queue()
for item in items:
    queue.put_nowait(item)

async def _worker(peer: PeerInfo) -> None:
    while True:
        batch = []
        for _ in range(batch_size):
            batch.append(queue.get_nowait())   # sort sur QueueEmpty
        if not batch:
            return
        results = await worker_fn(peer, batch)
        result_fn(results)

tasks = [asyncio.create_task(_worker(p)) for p in peers]
await asyncio.gather(*tasks)
```

**Caractéristiques** :
- Un worker par pair lancé via `asyncio.create_task()`
- Extraction par unité de `batch_size` depuis la file partagée (`get_nowait()` non bloquant)
- Les pairs rapides consomment plus de la file → équilibrage naturel de la charge
- `stats_lock` met à jour exclusivement `processed` / `errors`

---

## DisableAwareStrategy (v4.67.0)

Hérite de `BatchInferenceStrategy` et applique un filtre supplémentaire via l'overlay de désactivation de `MeshInferenceState`.

```python
class DisableAwareStrategy(BatchInferenceStrategy):
    def select_peers(self, inference_type, peers, mode="parallel"):
        base = super().select_peers(inference_type, peers, mode)
        return [
            p for p in base
            if not self._state.is_disabled(p.peer_id, inference_type)
        ]
```

- `super().select_peers()` applique le filtre en ligne/capability
- Ensuite, exclusion si la paire `(peer_id, inference_type)` est désactivée
- Utilisé pour suspendre temporairement un type spécifique d'un pair spécifique depuis le WebUI

---

## Persistance : data/mesh_inference_state.json

Persiste l'overlay de désactivation avec écriture atomique.

```json
{
  "version": 1,
  "disabled": {
    "<peer_id>": ["tagger", "clip"]
  }
}
```

- `persistence.save_state()` écrit dans un fichier `.tmp` puis remplace atomiquement avec `os.replace()`
- `persistence.load_state()` bascule sur un état vide en cas d'absence de fichier, de JSON corrompu ou d'incompatibilité de version
- Chargé une seule fois lors de `set_router()` (`_load_persistence_once()`) et injecté dans `DisableAwareStrategy`

---

## Fallback : Retour Automatique en Cas de Défaillance de Pair

```
Appel de dispatch_inference()
    ↓
_get_available_peers() → PeerRegistry.list_online()
    ↓
Si 0 pair :
    Émet un log d'avertissement et retourne {"status":"ok","processed":0,"errors":N}
    ↓
L'appelant détecte errors>0 et bascule sur un traitement local
```

- `PeerRegistry` passe à `status="offline"` si la vérification de vie du pair échoue
- `BatchInferenceStrategy.select_peers()` ne retourne que `status=="online"`
- Le nœud local est toujours inclus en tête de `all_peers`, donc en cas de défaillance totale des pairs distants, retour automatique au traitement local

---

## dispatch_sync : Pont d'Appel Synchrone

Pont pour appeler `InferenceRouter` depuis un thread d'arrière-plan (sans boucle d'événements).

```python
# core/mesh_inference/dispatch_sync.py
def dispatch_inference_sync(router, inference_type, items, **kwargs):
    async def _run():
        return await router.dispatch_inference(inference_type, items, **kwargs)
    return asyncio.run(_run())
```

**Attention :** non utilisable depuis l'intérieur d'une boucle `asyncio` existante. Dans une coroutine, utilisez directement `await router.dispatch_inference(...)`.

### Coordinateur de Batch Tagger

`run_tagger_batch()` est un utilitaire haut niveau utilisant `dispatch_inference_sync`, lançant un job d'étiquetage dans un thread d'arrière-plan.

```python
thread = threading.Thread(
    target=_tagger_batch_coordinator,
    args=(job, file_ids, limit, force, threshold),
    daemon=True,
    name="tagger-mesh-coordinator",
)
thread.start()
```

`job_manager` empêche les lancements doubles de job et sélectionne automatiquement les fichiers non étiquetés.

---

## Résumé de l'API Façade

```python
from core.mesh_inference import get_router, has_mesh, set_router

# Exemple d'utilisation
router = get_router()
if router is not None:
    result = await router.dispatch_inference(
        inference_type="tagger",
        items=file_paths,
        batch_size=32,
        worker_fn=my_worker,
        result_fn=save_results,
        progress_fn=update_progress,
    )
```

| Fonction | Description |
|---|---|
| `get_router()` | Retourne l'InferenceRouter actif (None si non enregistré) |
| `has_mesh()` | Retourne en bool si la maille est disponible |
| `set_router(router)` | Appelé par CoworkManager au démarrage/arrêt. Au démarrage, charge la persistance et injecte la stratégie |

---

## Fichiers Associés

- `core/mesh_inference/__init__.py` — Façade
- `core/mesh_inference/strategy.py` — DisableAwareStrategy
- `core/mesh_inference/persistence.py` — Persistance JSON
- `core/mesh_inference/dispatch_sync.py` — Pont synchrone + batch tagger
- `extensions/builtin_lan_cowork/core_impl/inference/router.py` — InferenceRouter + work-stealing
- `extensions/builtin_lan_cowork/core_impl/inference/state.py` — InferenceState
- `data/mesh_inference_state.json` — Destination de persistance de l'overlay de désactivation
