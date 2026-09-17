# Architettura di Inferenza Mesh

> Versione target: v4.67.0 e successive

## Panoramica

Il sistema di inferenza mesh è un meccanismo per cui più nodi yu_ai_manager su LAN cooperano per elaborare in modo distribuito i task di inferenza (tagger / clip / yolo / whisper). Combina il rilevamento automatico tramite mDNS, il work-stealing tramite asyncio.Queue e i filtri di disabilitazione per nodo per scalare orizzontalmente senza configurazione.

---

## Architettura Complessiva

```
┌─────────────────────────────────────────────────┐
│                 CoworkManager                   │
│  Genera InferenceRouter all'avvio e             │
│  registra in core.mesh_inference.set_router()   │
└────────────────────┬────────────────────────────┘
                     │
          ┌──────────▼──────────┐
          │   InferenceRouter   │  extensions/builtin_lan_cowork/
          │                     │  core_impl/inference/router.py
          │  _local_peer        │
          │  _registry ─────────┼──► PeerRegistry (lista peer LAN)
          │  _strategy ─────────┼──► DisableAwareStrategy
          └──────────┬──────────┘
                     │ dispatch_inference()
          ┌──────────▼──────────┐
          │   asyncio.Queue     │  coda work-stealing
          │   item, item, ...   │
          └──┬───────────┬──────┘
             │           │
       ┌─────▼──┐   ┌────▼────┐
       │ peer A │   │ peer B  │   (worker concorrenti)
       │(local) │   │(remote) │
       └────────┘   └─────────┘
```

### Responsabilità dei Componenti

| Componente | Posizione | Responsabilità |
|-----------|-----------|----------------|
| `core.mesh_inference` | `core/mesh_inference/__init__.py` | Facade: get_router / set_router |
| `InferenceRouter` | `extensions/builtin_lan_cowork/…/router.py` | Distribuzione batch, work-stealing |
| `PeerRegistry` | `extensions/builtin_lan_cowork/…/registry.py` | Gestione peer, determinazione online |
| `DisableAwareStrategy` | `core/mesh_inference/strategy.py` | Filtro disabilitazione per peer per tipo |
| `InferenceState` | `extensions/builtin_lan_cowork/…/state.py` | Riferimento motore locale |
| `dispatch_sync` | `core/mesh_inference/dispatch_sync.py` | Bridge async→thread |
| `persistence` | `core/mesh_inference/persistence.py` | Persistenza JSON |

---

## Rilevamento Automatico Peer (mDNS Phase B)

Pubblicazione del servizio `_yu-ai._tcp.local.` sulla LAN e navigazione dello stesso servizio per il rilevamento reciproco.

```
nodo A                               nodo B
  │  ── mDNS advertise ──►           │
  │  ◄── mDNS browse ────            │
  │                                  │
  │  ── GET /api/mdns/identity ──►   │
  │  ◄── {node_id, capabilities} ─── │
  │                                  │
  │  Registrazione in PeerRegistry   │
```

---

## Tipi di Inferenza e Backend

`InferenceState.get_inference_types()` restituisce stringhe che vengono impostate in `PeerInfo.inference_types` e diventano il criterio di routing.

| Tipo di Inferenza | Backend | Utilizzo |
|------------------|---------|----------|
| `tagger` | ONNX (WD14 ecc.) / Hailo NPU | Tagging immagini |
| `clip` | ONNX / Hailo / remoto | Vettori embedding immagini |
| `yolo` | ONNX / Hailo | Rilevamento oggetti |
| `whisper` | faster-whisper / remoto | Trascrizione audio |
| `hailo` | Hailo-10H vdevice | Accesso diretto dispositivo Hailo |
| `llm` | OpenAI-compat / Ollama | Inferenza LLM |

---

## Algoritmo Work-Stealing

```python
# router.py (schema)
queue: asyncio.Queue = asyncio.Queue()
for item in items:
    queue.put_nowait(item)

async def _worker(peer: PeerInfo) -> None:
    while True:
        batch = []
        for _ in range(batch_size):
            batch.append(queue.get_nowait())   # esce con QueueEmpty
        if not batch:
            return
        results = await worker_fn(peer, batch)
        result_fn(results)

tasks = [asyncio.create_task(_worker(p)) for p in peers]
await asyncio.gather(*tasks)
```

**Caratteristiche:**
- Un worker per peer avviato con `asyncio.create_task()`
- Prelievo a unità `batch_size` dalla coda condivisa (`get_nowait()` non bloccante)
- I peer più veloci elaborano più dalla coda → bilanciamento naturale del carico

---

## DisableAwareStrategy (v4.67.0)

Eredita da `BatchInferenceStrategy` e applica filtri aggiuntivi con l'overlay di disabilitazione di `MeshInferenceState`.

```python
class DisableAwareStrategy(BatchInferenceStrategy):
    def select_peers(self, inference_type, peers, mode="parallel"):
        base = super().select_peers(inference_type, peers, mode)
        return [
            p for p in base
            if not self._state.is_disabled(p.peer_id, inference_type)
        ]
```

---

## Persistenza: data/mesh_inference_state.json

Persistenza dell'overlay di disabilitazione con scrittura atomica.

```json
{
  "version": 1,
  "disabled": {
    "<peer_id>": ["tagger", "clip"]
  }
}
```

---

## Fallback: Ripristino Automatico al Fallimento del Peer

```
chiamata dispatch_inference()
    ↓
_get_available_peers() → PeerRegistry.list_online()
    ↓
Se 0 peer:
    output log di avviso e ritorna {"status":"ok","processed":0,"errors":N}
    ↓
Il chiamante rileva errors>0 e fa fallback all'elaborazione locale
```

---

## dispatch_sync: Bridge di Chiamata Sincrona

Bridge per chiamare `InferenceRouter` da thread in background (senza event loop).

```python
# core/mesh_inference/dispatch_sync.py
def dispatch_inference_sync(router, inference_type, items, **kwargs):
    async def _run():
        return await router.dispatch_inference(inference_type, items, **kwargs)
    return asyncio.run(_run())
```

**Nota:** Non utilizzabile dall'interno di un `asyncio` loop esistente. All'interno di coroutine usare direttamente `await router.dispatch_inference(...)`.

---

## Riepilogo Facade API

```python
from core.mesh_inference import get_router, has_mesh, set_router

# Esempio di utilizzo
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

| Funzione | Descrizione |
|----------|-------------|
| `get_router()` | Restituisce l'InferenceRouter attivo (None se non registrato) |
| `has_mesh()` | Restituisce bool se mesh disponibile |
| `set_router(router)` | Chiamata da CoworkManager all'avvio/stop. All'avvio esegue caricamento persistenza e iniezione strategia |

## Concetto

Distribuisci task AI (YOLO, CLIP, LLM) tra più nodi peer.
Bilanciamento automatico secondo disponibilità.

## Topologia

- **Chief node**: Coordina task
- **Worker node**: Esegue modelli locali
- **Mesh**: Comunicazione peer-to-peer via mDNS

## Configurazione

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "mesh_inference": {
        "enabled": true,
        "models": [
          "yolo",
          "clip",
          "llm"
        ],
        "prefer_local": true,
        "fallback_remote": true
      }
    }
  }
}
```

## Performance

- Rilevamento automatico capacità peer
- Failover su indisponibilità
- Caching risultato locale
