# Arquitetura de Mesh Inference

> Versão alvo: v4.67.0 ou superior

## Visão geral

O sistema de mesh inference faz com que múltiplos nós do yu_ai_manager em uma LAN cooperem para processar tarefas de inferência (tagger / clip / yolo / whisper) de forma distribuída. Combinando descoberta automática via mDNS, work-stealing com `asyncio.Queue` e filtro de desativação por nó, escala horizontalmente sem configurações.

---

## Arquitetura geral

```
┌─────────────────────────────────────────────────┐
│                 CoworkManager                   │
│  cria o InferenceRouter na inicialização        │
│  e registra em core.mesh_inference.set_router() │
└────────────────────┬────────────────────────────┘
                     │
          ┌──────────▼──────────┐
          │   InferenceRouter   │  extensions/builtin_lan_cowork/
          │                     │  core_impl/inference/router.py
          │  _local_peer        │
          │  _registry ─────────┼──► PeerRegistry (lista de peers da LAN)
          │  _strategy ─────────┼──► DisableAwareStrategy
          └──────────┬──────────┘
                     │ dispatch_inference()
          ┌──────────▼──────────┐
          │   asyncio.Queue     │  fila de work-stealing
          │   item, item, ...   │
          └──┬───────────┬──────┘
             │           │
       ┌─────▼──┐   ┌────▼────┐
       │ peer A │   │ peer B  │   (workers em paralelo)
       │(local) │   │(remote) │
       └────────┘   └─────────┘
```

### Responsabilidades dos componentes

| Componente | Local | Responsabilidade |
|---|---|---|
| `core.mesh_inference` | `core/mesh_inference/__init__.py` | Facade: get_router / set_router |
| `InferenceRouter` | `extensions/builtin_lan_cowork/…/router.py` | Distribuição em lote / work-stealing |
| `PeerRegistry` | `extensions/builtin_lan_cowork/…/registry.py` | Gestão de peers e verificação de online |
| `DisableAwareStrategy` | `core/mesh_inference/strategy.py` | Filtro de desativação per-peer-per-type |
| `InferenceState` | `extensions/builtin_lan_cowork/…/state.py` | Referência ao engine local |
| `dispatch_sync` | `core/mesh_inference/dispatch_sync.py` | Ponte async→thread |
| `persistence` | `core/mesh_inference/persistence.py` | Persistência em JSON |

---

## Descoberta automática de peers (mDNS Fase B)

Anuncia o serviço `_yu-ai._tcp.local.` na LAN e faz browse desse mesmo serviço para descoberta mútua.

```
node A                               node B
  │  ── mDNS advertise ──►           │
  │  ◄── mDNS browse ────            │
  │                                  │
  │  ── GET /api/mdns/identity ──►   │
  │  ◄── {node_id, capabilities} ─── │
  │                                  │
  │  registra em PeerRegistry        │
```

Detalhes do fluxo de descoberta:
1. `LlmRouterMdnsBridge` recebe o evento mDNS
2. Confirma se o peer é um yu_ai_manager real via verificação HTTP em `/api/mdns/identity`
3. Após verificação bem-sucedida, adiciona o peer ao `PeerRegistry`
4. A lista de tipos retornada por `InferenceState.get_inference_types()` é refletida em `PeerInfo.inference_types`

---

## Tipos de inferência e backends

A string retornada por `InferenceState.get_inference_types()` é definida em `PeerInfo.inference_types` e serve de critério de roteamento.

| Tipo de inferência | Backend | Uso |
|---|---|---|
| `tagger` | ONNX (WD14 etc.) / Hailo NPU | Tagueamento de imagem |
| `clip` | ONNX / Hailo / remoto | Vetores de embedding de imagem |
| `yolo` | ONNX / Hailo | Detecção de objetos |
| `whisper` | faster-whisper / remoto | Transcrição de áudio |
| `hailo` | Hailo-10H vdevice | Acesso direto ao dispositivo Hailo |
| `llm` | Compatível com OpenAI / Ollama | Inferência de LLM |

Tipos cujo engine é `None` não são incluídos na lista de `get_inference_types()` e, portanto, não são roteados para esse peer.

---

## Algoritmo de work-stealing

```python
# router.py (esquema)
queue: asyncio.Queue = asyncio.Queue()
for item in items:
    queue.put_nowait(item)

async def _worker(peer: PeerInfo) -> None:
    while True:
        batch = []
        for _ in range(batch_size):
            batch.append(queue.get_nowait())   # sai com QueueEmpty
        if not batch:
            return
        results = await worker_fn(peer, batch)
        result_fn(results)

tasks = [asyncio.create_task(_worker(p)) for p in peers]
await asyncio.gather(*tasks)
```

**Características:**
- Um worker por peer é iniciado com `asyncio.create_task()`
- Retira em unidades de `batch_size` da fila compartilhada (não-bloqueante com `get_nowait()`)
- Peers mais rápidos consomem mais da fila → balanceamento natural
- `stats_lock` garante atualização exclusiva de `processed` / `errors`

---

## DisableAwareStrategy (v4.67.0)

Herda de `BatchInferenceStrategy` e aplica filtro adicional pelo overlay de desativação do `MeshInferenceState`.

```python
class DisableAwareStrategy(BatchInferenceStrategy):
    def select_peers(self, inference_type, peers, mode="parallel"):
        base = super().select_peers(inference_type, peers, mode)
        return [
            p for p in base
            if not self._state.is_disabled(p.peer_id, inference_type)
        ]
```

- `super().select_peers()` aplica filtros de online e capability
- Depois, exclui pares `(peer_id, inference_type)` marcados como desativados
- Usado para suspender temporariamente um tipo específico em um peer específico pela WebUI

---

## Persistência: data/mesh_inference_state.json

O overlay de desativação é persistido com escrita atômica.

```json
{
  "version": 1,
  "disabled": {
    "<peer_id>": ["tagger", "clip"]
  }
}
```

- `persistence.save_state()` escreve em um arquivo `.tmp` e substitui atomicamente com `os.replace()`
- `persistence.load_state()` cai em estado vazio tanto na ausência do arquivo, quanto em JSON corrompido, quanto em versão incompatível
- Ao chamar `set_router()`, o carregamento ocorre apenas uma vez (`_load_persistence_once()`) e é injetado no `DisableAwareStrategy`

---

## Fallback: recuperação automática em caso de falha de peer

```
chamada de dispatch_inference()
    ↓
_get_available_peers() → PeerRegistry.list_online()
    ↓
se houver 0 peers:
    grava aviso no log e retorna {"status":"ok","processed":0,"errors":N}
    ↓
o chamador detecta errors>0 e faz fallback para processamento local
```

- Quando a verificação de vivacidade falha, o `PeerRegistry` move o peer para `status="offline"`
- `BatchInferenceStrategy.select_peers()` só retorna os com `status=="online"`
- O nó local sempre consta no topo de `all_peers`, então mesmo que todos os remotos caiam, há fallback automático para processamento local

---

## dispatch_sync: ponte para chamadas síncronas

Ponte para chamar o `InferenceRouter` a partir de threads em background (sem event loop).

```python
# core/mesh_inference/dispatch_sync.py
def dispatch_inference_sync(router, inference_type, items, **kwargs):
    async def _run():
        return await router.dispatch_inference(inference_type, items, **kwargs)
    return asyncio.run(_run())
```

**Atenção:** não pode ser usado dentro de um loop `asyncio` já existente. Dentro de corrotinas, use diretamente `await router.dispatch_inference(...)`.

### Coordenador de batch do tagger

`run_tagger_batch()` é um utilitário de alto nível que usa `dispatch_inference_sync` e inicia um job de tagueamento em uma thread de background.

```python
thread = threading.Thread(
    target=_tagger_batch_coordinator,
    args=(job, file_ids, limit, force, threshold),
    daemon=True,
    name="tagger-mesh-coordinator",
)
thread.start()
```

O `job_manager` impede disparo duplicado de jobs e seleciona automaticamente arquivos não tagueados.

---

## Resumo da API de facade

```python
from core.mesh_inference import get_router, has_mesh, set_router

# Exemplo de uso
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

| Função | Descrição |
|---|---|
| `get_router()` | Retorna o InferenceRouter ativo (None se não registrado) |
| `has_mesh()` | Retorna bool indicando se a mesh está disponível |
| `set_router(router)` | Chamado pelo CoworkManager na inicialização/encerramento. Na inicialização, executa carga da persistência e injeta a estratégia |

---

## Arquivos relacionados

- `core/mesh_inference/__init__.py` — facade
- `core/mesh_inference/strategy.py` — DisableAwareStrategy
- `core/mesh_inference/persistence.py` — persistência em JSON
- `core/mesh_inference/dispatch_sync.py` — ponte síncrona + batch do tagger
- `extensions/builtin_lan_cowork/core_impl/inference/router.py` — InferenceRouter + work-stealing
- `extensions/builtin_lan_cowork/core_impl/inference/state.py` — InferenceState
- `data/mesh_inference_state.json` — destino da persistência do overlay de desativação
