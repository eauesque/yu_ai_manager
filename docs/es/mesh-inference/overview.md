# Arquitectura de inferencia distribuida

> Versión objetivo: v4.67.0 o posterior

## Descripción general

Sistema inferencia distribuida permite múltiples nodos yu_ai_manager en LAN cooperar procesando tareas inferencia (tagger / clip / yolo / whisper). Combina descubrimiento automático mDNS, robo de trabajo usando asyncio.Queue, y filtro deshabilitación por nodo, escalando horizontalmente sin configuración.

---

## Arquitectura general

```
┌─────────────────────────────────────────────────┐
│                 CoworkManager                   │
│  Generar InferenceRouter al iniciar             │
│  Registrar en core.mesh_inference.set_router()  │
└────────────────────┬────────────────────────────┘
                     │
          ┌──────────▼──────────┐
          │   InferenceRouter   │  extensions/builtin_lan_cowork/
          │                     │  core_impl/inference/router.py
          │  _local_peer        │
          │  _registry ─────────┼──► PeerRegistry (lista peers LAN)
          │  _strategy ─────────┼──► DisableAwareStrategy
          └──────────┬──────────┘
                     │ dispatch_inference()
          ┌──────────▼──────────┐
          │   asyncio.Queue     │  cola robo trabajo
          │   item, item, ...   │
          └──┬───────────┬──────┘
             │           │
       ┌─────▼──┐   ┌────▼────┐
       │ peer A │   │ peer B  │   (workers paralelos)
       │(local) │   │(remote) │
       └────────┘   └─────────┘
```

### Responsabilidades componentes

| Componente | Ubicación | Responsabilidad |
|---|---|---|
| `core.mesh_inference` | `core/mesh_inference/__init__.py` | Fachada: get_router / set_router |
| `InferenceRouter` | `extensions/builtin_lan_cowork/…/router.py` | Distribución lotes, robo trabajo |
| `PeerRegistry` | `extensions/builtin_lan_cowork/…/registry.py` | Gestión peers, determinar disponibilidad |
| `DisableAwareStrategy` | `core/mesh_inference/strategy.py` | Filtro deshabilitación per-peer-per-type |
| `InferenceState` | `extensions/builtin_lan_cowork/…/state.py` | Referencia motor local |
| `dispatch_sync` | `core/mesh_inference/dispatch_sync.py` | Puente async→thread |
| `persistence` | `core/mesh_inference/persistence.py` | Persistencia JSON |

---

## Descubrimiento automático peers (mDNS Phase B)

Anunciar servicio `_yu-ai._tcp.local.` en LAN, descubrirse mutuamente navegando servicio mismo.

```
nodo A                               nodo B
  │  ── anuncio mDNS ──►             │
  │  ◄── navegar mDNS ────           │
  │                                  │
  │  ── GET /api/mdns/identity ──►   │
  │  ◄── {node_id, capabilities} ─── │
  │                                  │
  │  Registrar en PeerRegistry        │
```

Detalles flujo descubrimiento:
1. `LlmRouterMdnsBridge` recibe evento mDNS
2. Verificación HTTP `/api/mdns/identity` confirma peer es yu_ai_manager real
3. Después verificación exitosa, agregar peer a `PeerRegistry`
4. Lista tipos devueltos `InferenceState.get_inference_types()` se refleja en `PeerInfo.inference_types`

---

## Tipos inferencia y backends

Cadena devuelta `InferenceState.get_inference_types()` se configura en `PeerInfo.inference_types`, base criterio enrutamiento.

| Tipo inferencia | Backend | Uso |
|---|---|---|
| `tagger` | ONNX (WD14 etc) / Hailo NPU | Etiquetado imagen |
| `clip` | ONNX / Hailo / remoto | Vector incrustación imagen |
| `yolo` | ONNX / Hailo | Detección objeto |
| `whisper` | faster-whisper / remoto | Transcripción voz |
| `hailo` | Hailo-10H vdevice | Acceso directo dispositivo Hailo |
| `llm` | OpenAI-compat / Ollama | Inferencia LLM |

Motor `None` para tipo no incluido en lista `get_inference_types()`, por lo que ese peer no recibirá enrutamiento.

---

## Algoritmo robo trabajo

```python
# router.py (esquema)
queue: asyncio.Queue = asyncio.Queue()
for item in items:
    queue.put_nowait(item)

async def _worker(peer: PeerInfo) -> None:
    while True:
        batch = []
        for _ in range(batch_size):
            batch.append(queue.get_nowait())   # QueueEmpty sale
        if not batch:
            return
        results = await worker_fn(peer, batch)
        result_fn(results)

tasks = [asyncio.create_task(_worker(p)) for p in peers]
await asyncio.gather(*tasks)
```

**Características:**
- Lanzar 1 worker por peer con `asyncio.create_task()`
- Extraer unidades `batch_size` de cola compartida (`get_nowait()` no-blocking)
- Peer rápido consume más cola → equilibrio carga natural
- `stats_lock` actualiza exclusivamente `processed` / `errors`

---

## DisableAwareStrategy (v4.67.0)

Hereda `BatchInferenceStrategy`, agrega filtro con overlay deshabilitación `MeshInferenceState`.

```python
class DisableAwareStrategy(BatchInferenceStrategy):
    def select_peers(self, inference_type, peers, mode="parallel"):
        base = super().select_peers(inference_type, peers, mode)
        return [
            p for p in base
            if not self._state.is_disabled(p.peer_id, inference_type)
        ]
```

- `super().select_peers()` aplica filtro disponibilidad y capability
- Después, excluir si pareja `(peer_id, inference_type)` está deshabilitada
- Usado para pausar tipo específico de peer específico desde WebUI

---

## Persistencia: data/mesh_inference_state.json

Persistir overlay deshabilitación con escritura atómica.

```json
{
  "version": 1,
  "disabled": {
    "<peer_id>": ["tagger", "clip"]
  }
}
```

- `persistence.save_state()` escribe en archivo `.tmp` luego reemplazo atómico `os.replace()`
- `persistence.load_state()` fallback a estado vacío si archivo ausente, JSON corrompido, versión no coincide
- Cargar una sola vez al `set_router()` (`_load_persistence_once()`), inyectar en `DisableAwareStrategy`

---

## Fallback: recuperación automática fallo peer

```
Llamada dispatch_inference()
    ↓
_get_available_peers() → PeerRegistry.list_online()
    ↓
Si 0 peers:
    Registrar advertencia, retorna {"status":"ok","processed":0,"errors":N}
    ↓
Llamador detecta errors>0 fallback a procesamiento local
```

- `PeerRegistry` transiciona a `status="offline"` si verificación vida falla
- `BatchInferenceStrategy.select_peers()` retorna solo `status=="online"`
- Nodo local siempre incluido como primer elemento `all_peers`, fallo remoto total recupera automáticamente local

---

## dispatch_sync: puente llamada sincrónica

Puente para llamar `InferenceRouter` desde thread background (sin event loop).

```python
# core/mesh_inference/dispatch_sync.py
def dispatch_inference_sync(router, inference_type, items, **kwargs):
    async def _run():
        return await router.dispatch_inference(inference_type, items, **kwargs)
    return asyncio.run(_run())
```

**Advertencia:** No usar dentro loop `asyncio` existente. Dentro corutina usar `await router.dispatch_inference(...)` directo.

### Coordinador lotes tagger

`run_tagger_batch()` utilidad nivel alto usando `dispatch_inference_sync`, lanzar trabajo etiquetado en thread background.

```python
thread = threading.Thread(
    target=_tagger_batch_coordinator,
    args=(job, file_ids, limit, force, threshold),
    daemon=True,
    name="tagger-mesh-coordinator",
)
thread.start()
```

`job_manager` previene lanzamiento duplicado job, auto-selecciona archivos no etiquetados.

---

## Resumen API fachada

```python
from core.mesh_inference import get_router, has_mesh, set_router

# Ejemplo uso
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

| Función | Descripción |
|---|---|
| `get_router()` | Retornar InferenceRouter activo (None si no registrado) |
| `has_mesh()` | Retornar bool si mesh disponible |
| `set_router(router)` | CoworkManager llama al inicio/parada. Al inicio ejecuta carga persistencia inyección estrategia |

---

## Archivos relacionados

- `core/mesh_inference/__init__.py` — Fachada
- `core/mesh_inference/strategy.py` — DisableAwareStrategy
- `core/mesh_inference/persistence.py` — Persistencia JSON
- `core/mesh_inference/dispatch_sync.py` — Puente sincrónico + lotes tagger
- `extensions/builtin_lan_cowork/core_impl/inference/router.py` — InferenceRouter + robo trabajo
- `extensions/builtin_lan_cowork/core_impl/inference/state.py` — InferenceState
- `data/mesh_inference_state.json` — Destino persistencia overlay deshabilitación
