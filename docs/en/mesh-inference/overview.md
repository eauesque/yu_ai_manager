# Mesh Inference Architecture

> Target version: v4.67.0 and later

## Overview

The mesh inference system enables multiple yu_ai_manager nodes on a LAN to collaboratively distribute inference tasks (tagger / clip / yolo / whisper). It combines mDNS auto-discovery, work-stealing via asyncio.Queue, and per-node disable filters to achieve zero-configuration horizontal scaling.

---

## Overall Architecture

```
┌─────────────────────────────────────────────────┐
│                 CoworkManager                   │
│  Creates InferenceRouter on startup and         │
│  registers it via core.mesh_inference.set_router│
└────────────────────┬────────────────────────────┘
                     │
          ┌──────────▼──────────┐
          │   InferenceRouter   │  extensions/builtin_lan_cowork/
          │                     │  core_impl/inference/router.py
          │  _local_peer        │
          │  _registry ─────────┼──► PeerRegistry (LAN peer list)
          │  _strategy ─────────┼──► DisableAwareStrategy
          └──────────┬──────────┘
                     │ dispatch_inference()
          ┌──────────▼──────────┐
          │   asyncio.Queue     │  work-stealing queue
          │   item, item, ...   │
          └──┬───────────┬──────┘
             │           │
       ┌─────▼──┐   ┌────▼────┐
       │ peer A │   │ peer B  │   (parallel workers)
       │(local) │   │(remote) │
       └────────┘   └─────────┘
```

### Component Responsibilities

| Component | Location | Responsibility |
|---|---|---|
| `core.mesh_inference` | `core/mesh_inference/__init__.py` | Facade: get_router / set_router |
| `InferenceRouter` | `extensions/builtin_lan_cowork/…/router.py` | Batch distribution / work-stealing |
| `PeerRegistry` | `extensions/builtin_lan_cowork/…/registry.py` | Peer management / online status |
| `DisableAwareStrategy` | `core/mesh_inference/strategy.py` | Per-peer-per-type disable filter |
| `InferenceState` | `extensions/builtin_lan_cowork/…/state.py` | Local engine references |
| `dispatch_sync` | `core/mesh_inference/dispatch_sync.py` | async-to-thread bridge |
| `persistence` | `core/mesh_inference/persistence.py` | JSON persistence |

---

## Peer Auto-discovery (mDNS Phase B)

Nodes advertise the `_yu-ai._tcp.local.` service on the LAN and browse for the same service to discover each other.

```
node A                               node B
  │  ── mDNS advertise ──►           │
  │  ◄── mDNS browse ────            │
  │                                  │
  │  ── GET /api/mdns/identity ──►   │
  │  ◄── {node_id, capabilities} ─── │
  │                                  │
  │  Register in PeerRegistry        │
```

Discovery flow details:
1. `LlmRouterMdnsBridge` receives mDNS events
2. HTTP verification via `/api/mdns/identity` confirms the peer is a genuine yu_ai_manager instance
3. After successful verification, the peer is added to `PeerRegistry`
4. The type list returned by `InferenceState.get_inference_types()` is reflected in `PeerInfo.inference_types`

---

## Inference Types and Backends

The strings returned by `InferenceState.get_inference_types()` are set in `PeerInfo.inference_types` and serve as the basis for routing.

| Inference Type | Backend | Purpose |
|---|---|---|
| `tagger` | ONNX (WD14, etc.) / Hailo NPU | Image tagging |
| `clip` | ONNX / Hailo / remote | Image embedding vectors |
| `yolo` | ONNX / Hailo | Object detection |
| `whisper` | faster-whisper / remote | Speech-to-text |
| `hailo` | Hailo-10H vdevice | Direct Hailo device access |
| `llm` | OpenAI-compat / Ollama | LLM inference |

Types for which the engine is `None` are not included in the `get_inference_types()` list, so no routing is performed to that peer for those types.

---

## Work-stealing Algorithm

```python
# router.py (outline)
queue: asyncio.Queue = asyncio.Queue()
for item in items:
    queue.put_nowait(item)

async def _worker(peer: PeerInfo) -> None:
    while True:
        batch = []
        for _ in range(batch_size):
            batch.append(queue.get_nowait())   # breaks on QueueEmpty
        if not batch:
            return
        results = await worker_fn(peer, batch)
        result_fn(results)

tasks = [asyncio.create_task(_worker(p)) for p in peers]
await asyncio.gather(*tasks)
```

**Characteristics:**
- One worker per peer launched via `asyncio.create_task()`
- Items are taken from a shared queue in `batch_size` chunks (`get_nowait()` for non-blocking)
- Faster peers consume more from the queue, achieving natural load balancing
- `stats_lock` provides exclusive updates for `processed` / `errors`

---

## DisableAwareStrategy (v4.67.0)

Inherits from `BatchInferenceStrategy` and applies an additional filter using the `MeshInferenceState` disable overlay.

```python
class DisableAwareStrategy(BatchInferenceStrategy):
    def select_peers(self, inference_type, peers, mode="parallel"):
        base = super().select_peers(inference_type, peers, mode)
        return [
            p for p in base
            if not self._state.is_disabled(p.peer_id, inference_type)
        ]
```

- `super().select_peers()` applies online and capability filters
- Then, `(peer_id, inference_type)` pairs that are disabled are excluded
- Used to temporarily pause a specific type on a specific peer from the WebUI

---

## Persistence: data/mesh_inference_state.json

The disable overlay is persisted via atomic writes.

```json
{
  "version": 1,
  "disabled": {
    "<peer_id>": ["tagger", "clip"]
  }
}
```

- `persistence.save_state()` writes to a `.tmp` file then atomically replaces via `os.replace()`
- `persistence.load_state()` falls back to an empty state on file absence, JSON corruption, or version mismatch
- Loaded once during `set_router()` (`_load_persistence_once()`) and injected into `DisableAwareStrategy`

---

## Fallback: Automatic Recovery on Peer Failure

```
dispatch_inference() call
    ↓
_get_available_peers() → PeerRegistry.list_online()
    ↓
If 0 peers:
    Log a warning and return {"status":"ok","processed":0,"errors":N}
    ↓
The caller detects errors>0 and falls back to local processing
```

- `PeerRegistry` transitions a peer to `status="offline"` when a liveness check fails
- `BatchInferenceStrategy.select_peers()` only returns peers with `status=="online"`
- The local node is always first in `all_peers`, so local processing is automatically restored even if all remotes are down

---

## dispatch_sync: Synchronous Call Bridge

A bridge for calling `InferenceRouter` from background threads (without an event loop).

```python
# core/mesh_inference/dispatch_sync.py
def dispatch_inference_sync(router, inference_type, items, **kwargs):
    async def _run():
        return await router.dispatch_inference(inference_type, items, **kwargs)
    return asyncio.run(_run())
```

**Note:** Cannot be used from within an existing `asyncio` loop. Inside coroutines, use `await router.dispatch_inference(...)` directly.

### Tagger Batch Coordinator

`run_tagger_batch()` is a high-level utility using `dispatch_inference_sync` that launches tagging jobs in a background thread.

```python
thread = threading.Thread(
    target=_tagger_batch_coordinator,
    args=(job, file_ids, limit, force, threshold),
    daemon=True,
    name="tagger-mesh-coordinator",
)
thread.start()
```

The `job_manager` prevents duplicate job launches and automatically selects untagged files.

---

## Facade API Summary

```python
from core.mesh_inference import get_router, has_mesh, set_router

# Usage example
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

| Function | Description |
|---|---|
| `get_router()` | Returns the active InferenceRouter (None if not registered) |
| `has_mesh()` | Returns a bool indicating whether mesh is available |
| `set_router(router)` | Called by CoworkManager on startup/shutdown. Loads persistence and injects strategy on startup |

---

## Related Files

- `core/mesh_inference/__init__.py` -- Facade
- `core/mesh_inference/strategy.py` -- DisableAwareStrategy
- `core/mesh_inference/persistence.py` -- JSON persistence
- `core/mesh_inference/dispatch_sync.py` -- Synchronous bridge + tagger batch
- `extensions/builtin_lan_cowork/core_impl/inference/router.py` -- InferenceRouter + work-stealing
- `extensions/builtin_lan_cowork/core_impl/inference/state.py` -- InferenceState
- `data/mesh_inference_state.json` -- Disable overlay persistence location
