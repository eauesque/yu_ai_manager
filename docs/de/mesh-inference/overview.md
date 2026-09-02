# Mesh Inferenz Architektur

> Zielversion: v4.67.0 und später

## Übersicht

Mesh Inferenz System ermöglicht mehreren yu_ai_manager Knoten im LAN zu kooperieren um Inferenz-Tasks (tagger / clip / yolo / whisper) verteilt zu verarbeiten. Mit mDNS Auto-Discovery, asyncio.Queue Work-Stealing und pro-Knoten-Disablierung kombiniert, skaliert horizontal ohne Konfiguration.

---

## Gesamtarchitektur

```
┌─────────────────────────────────────────────────┐
│                 CoworkManager                   │
│  Erstellt beim Start InferenceRouter            │
│  registriert bei core.mesh_inference.set_router│
└────────────────────┬────────────────────────────┘
                     │
          ┌──────────▼──────────┐
          │   InferenceRouter   │  extensions/builtin_lan_cowork/
          │                     │  core_impl/inference/router.py
          │  _local_peer        │
          │  _registry ─────────┼──► PeerRegistry (LAN Peers)
          │  _strategy ─────────┼──► DisableAwareStrategy
          └──────────┬──────────┘
                     │ dispatch_inference()
          ┌──────────▼──────────┐
          │   asyncio.Queue     │  work-stealing Queue
          │   item, item, ...   │
          └──┬───────────┬──────┘
             │           │
       ┌─────▼──┐   ┌────▼────┐
       │ peer A │   │ peer B  │   (Parallel-Worker)
       │(local) │   │(remote) │
       └────────┘   └─────────┘
```

### Komponenten-Verantwortung

| Komponente | Ort | Verantwortung |
|---|---|---|
| `core.mesh_inference` | `core/mesh_inference/__init__.py` | Fassade: get_router / set_router |
| `InferenceRouter` | `extensions/builtin_lan_cowork/…/router.py` | Batch-Verteilung, Work-Stealing |
| `PeerRegistry` | `extensions/builtin_lan_cowork/…/registry.py` | Peer-Verwaltung, Online-Check |
| `DisableAwareStrategy` | `core/mesh_inference/strategy.py` | Pro-Peer-Pro-Typ Disablierung-Filter |
| `InferenceState` | `extensions/builtin_lan_cowork/…/state.py` | Lokale Engine-Referenz |
| `dispatch_sync` | `core/mesh_inference/dispatch_sync.py` | Async→Thread Bridge |
| `persistence` | `core/mesh_inference/persistence.py` | JSON-Persistierung |

---

## Peer Auto-Discovery (mDNS Phase B)

`_yu-ai._tcp.local.` Service wird im LAN advertised und gleicher Service wird durchsucht für gegenseitige Entdeckung.

```
node A                               node B
  │  ── mDNS advertise ──►           │
  │  ◄── mDNS browse ────            │
  │                                  │
  │  ── GET /api/mdns/identity ──►   │
  │  ◄── {node_id, capabilities} ─── │
  │                                  │
  │  In PeerRegistry registriert     │
```

Discovery-Fluss:
1. `LlmRouterMdnsBridge` empfängt mDNS Events
2. `/api/mdns/identity` HTTP Verification ob Peer echter yu_ai_manager
3. Nach Verify Erfolg Peer zu `PeerRegistry` hinzufügen
4. `InferenceState.get_inference_types()` gibt zurück Type-Liste wird zu `PeerInfo.inference_types` reflektiert

---

## Inferenz-Typen und Backends

`InferenceState.get_inference_types()` returned String wird zu `PeerInfo.inference_types` setzen, wird Routing-Basis.

| Inferenz-Typ | Backend | Zweck |
|---|---|---|
| `tagger` | ONNX (WD14 etc.) / Hailo NPU | Bild-Tags |
| `clip` | ONNX / Hailo / Remote | Bild-Embedding-Vektoren |
| `yolo` | ONNX / Hailo | Objekt-Detektion |
| `whisper` | faster-whisper / Remote | Sprache-Transkription |
| `hailo` | Hailo-10H vdevice | Hailo Direct Device Access |
| `llm` | OpenAI-compat / Ollama | LLM Inferenz |

Engine `None` Type nicht in `get_inference_types()` Liste enthalten, daher wird dieser Peer nicht für diesen Type geroutet.

---

## Work-Stealing Algorithmus

```python
# router.py (Übersicht)
queue: asyncio.Queue = asyncio.Queue()
for item in items:
    queue.put_nowait(item)

async def _worker(peer: PeerInfo) -> None:
    while True:
        batch = []
        for _ in range(batch_size):
            batch.append(queue.get_nowait())   # QueueEmpty exit
        if not batch:
            return
        results = await worker_fn(peer, batch)
        result_fn(results)

tasks = [asyncio.create_task(_worker(p)) for p in peers]
await asyncio.gather(*tasks)
```

**Charakteristiken:**
- Pro-Peer ein Worker mit `asyncio.create_task()` gestartet
- Shared Queue `batch_size` Einheiten extrahieren (`get_nowait()` non-blocking)
- Schneller Peer verbraucht mehr Queue → Natürliche Last-Ausgleich
- `stats_lock` exclusive `processed` / `errors` Update

---

## DisableAwareStrategy (v4.67.0)

Erbt `BatchInferenceStrategy`, fügt pro-Knoten-Disablierung-Overlay Filter hinzu.

```python
class DisableAwareStrategy(BatchInferenceStrategy):
    def select_peers(self, inference_type, peers, mode="parallel"):
        base = super().select_peers(inference_type, peers, mode)
        return [
            p for p in base
            if not self._state.is_disabled(p.peer_id, inference_type)
        ]
```

- `super().select_peers()` wendet Online & Capability-Filter an
- Dann `(peer_id, inference_type)` Paar disabliert ausschließen
- WebUI-Use für temporär einzelne Peer spezifische Type pausieren

---

## Persistierung: data/mesh_inference_state.json

Disablierung-Overlay persistent mit atomic write.

```json
{
  "version": 1,
  "disabled": {

