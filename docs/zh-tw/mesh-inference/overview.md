# 網狀推論架構

> 適用版本：v4.67.0 以後

## 概述

網狀推論系統是一種讓區域網路上的多個 yu_ai_manager 節點協同進行推論任務（tagger / clip / yolo / whisper）分散處理的機制。結合 mDNS 自動發現、使用 asyncio.Queue 的工作竊取，以及節點級停用篩選，無需設定即可水平擴展。

---

## 整體架構

```
┌─────────────────────────────────────────────────┐
│                 CoworkManager                   │
│  啟動時產生 InferenceRouter 並                   │
│  註冊至 core.mesh_inference.set_router()        │
└────────────────────┬────────────────────────────┘
                     │
          ┌──────────▼──────────┐
          │   InferenceRouter   │  extensions/builtin_lan_cowork/
          │                     │  core_impl/inference/router.py
          │  _local_peer        │
          │  _registry ─────────┼──► PeerRegistry（LAN peer 列表）
          │  _strategy ─────────┼──► DisableAwareStrategy
          └──────────┬──────────┘
                     │ dispatch_inference()
          ┌──────────▼──────────┐
          │   asyncio.Queue     │  work-stealing 佇列
          │   item, item, ...   │
          └──┬───────────┬──────┘
             │           │
       ┌─────▼──┐   ┌────▼────┐
       │ peer A │   │ peer B  │   （並行 worker）
       │(local) │   │(remote) │
       └────────┘   └─────────┘
```

### 元件職責

| 元件 | 位置 | 職責 |
|---|---|---|
| `core.mesh_inference` | `core/mesh_inference/__init__.py` | 外觀模式：get_router / set_router |
| `InferenceRouter` | `extensions/builtin_lan_cowork/…/router.py` | 批次分散、工作竊取 |
| `PeerRegistry` | `extensions/builtin_lan_cowork/…/registry.py` | peer 管理、上線判定 |
| `DisableAwareStrategy` | `core/mesh_inference/strategy.py` | per-peer-per-type 停用篩選 |
| `InferenceState` | `extensions/builtin_lan_cowork/…/state.py` | 本機引擎參照 |
| `dispatch_sync` | `core/mesh_inference/dispatch_sync.py` | async→thread 橋接 |
| `persistence` | `core/mesh_inference/persistence.py` | JSON 永久化 |

---

## Peer 自動發現（mDNS Phase B）

向區域網路 advertise `_yu-ai._tcp.local.` 服務，並瀏覽同一服務以進行相互發現。

```
node A                               node B
  │  ── mDNS advertise ──►           │
  │  ◄── mDNS browse ────            │
  │                                  │
  │  ── GET /api/mdns/identity ──►   │
  │  ◄── {node_id, capabilities} ─── │
  │                                  │
  │  註冊至 PeerRegistry              │
```

發現流程詳情：
1. `LlmRouterMdnsBridge` 接收 mDNS 事件
2. 透過 `/api/mdns/identity` HTTP 驗證確認 peer 是否為真正的 yu_ai_manager
3. 驗證成功後，將 peer 新增至 `PeerRegistry`
4. `InferenceState.get_inference_types()` 回傳的類型列表反映至 `PeerInfo.inference_types`

---

## 推論類型與後端

`InferenceState.get_inference_types()` 回傳的字串設定至 `PeerInfo.inference_types`，作為路由的基準。

| 推論類型 | 後端 | 用途 |
|---|---|---|
| `tagger` | ONNX（WD14 等）/ Hailo NPU | 圖片標記 |
| `clip` | ONNX / Hailo / 遠端 | 圖片嵌入向量 |
| `yolo` | ONNX / Hailo | 物件偵測 |
| `whisper` | faster-whisper / 遠端 | 語音轉文字 |
| `hailo` | Hailo-10H vdevice | Hailo 裝置直接存取 |
| `llm` | OpenAI-compat / Ollama | LLM 推論 |

引擎為 `None` 的類型不會包含在 `get_inference_types()` 的列表中，因此不會路由至該 peer。

---

## 工作竊取演算法

```python
# router.py（概要）
queue: asyncio.Queue = asyncio.Queue()
for item in items:
    queue.put_nowait(item)

async def _worker(peer: PeerInfo) -> None:
    while True:
        batch = []
        for _ in range(batch_size):
            batch.append(queue.get_nowait())   # QueueEmpty 時跳出
        if not batch:
            return
        results = await worker_fn(peer, batch)
        result_fn(results)

tasks = [asyncio.create_task(_worker(p)) for p in peers]
await asyncio.gather(*tasks)
```

**特性：**
- 每個 peer 以 `asyncio.create_task()` 啟動 1 個 worker
- 從共享佇列以 `batch_size` 為單位取出（`get_nowait()` 非阻塞）
- 速度快的 peer 會消耗更多佇列 → 自然的負載均衡
- 透過 `stats_lock` 互斥更新 `processed` / `errors`

---

## DisableAwareStrategy（v4.67.0）

繼承 `BatchInferenceStrategy`，以 `MeshInferenceState` 的停用覆蓋層進行額外篩選。

```python
class DisableAwareStrategy(BatchInferenceStrategy):
    def select_peers(self, inference_type, peers, mode="parallel"):
        base = super().select_peers(inference_type, peers, mode)
        return [
            p for p in base
            if not self._state.is_disabled(p.peer_id, inference_type)
        ]
```

- `super().select_peers()` 套用上線、capability 篩選
- 之後，若 `(peer_id, inference_type)` 配對已被停用則排除
- 用於從 WebUI 暫停特定 peer 的特定類型

---

## 永久化：data/mesh_inference_state.json

以原子寫入方式永久化停用覆蓋層。

```json
{
  "version": 1,
  "disabled": {
    "<peer_id>": ["tagger", "clip"]
  }
}
```

- `persistence.save_state()` 先寫入 `.tmp` 檔案，再以 `os.replace()` 原子替換
- `persistence.load_state()` 在檔案不存在、JSON 損毀、版本不符的任一情況下都會回退為空狀態
- `set_router()` 時僅載入一次（`_load_persistence_once()`），並注入至 `DisableAwareStrategy`

---

## 容錯：peer 故障時的自動恢復

```
dispatch_inference() 呼叫
    ↓
_get_available_peers() → PeerRegistry.list_online()
    ↓
peer 為 0 時：
    輸出警告日誌並回傳 {"status":"ok","processed":0,"errors":N}
    ↓
呼叫端偵測到 errors>0 後回退至本機處理
```

- `PeerRegistry` 在 peer 存活確認失敗時轉為 `status="offline"`
- `BatchInferenceStrategy.select_peers()` 僅回傳 `status=="online"` 的項目
- 本機節點始終位於 `all_peers` 的開頭，因此即使所有遠端都離線也會自動回退至本機處理

---

## dispatch_sync：同步呼叫橋接

用於從背景執行緒（無事件迴圈）呼叫 `InferenceRouter` 的橋接。

```python
# core/mesh_inference/dispatch_sync.py
def dispatch_inference_sync(router, inference_type, items, **kwargs):
    async def _run():
        return await router.dispatch_inference(inference_type, items, **kwargs)
    return asyncio.run(_run())
```

**注意：** 不可從既有的 `asyncio` 迴圈內使用。在協程中請直接使用 `await router.dispatch_inference(...)`。

### tagger 批次協調器

`run_tagger_batch()` 是使用 `dispatch_inference_sync` 的高階工具，在背景執行緒中啟動標記作業。

```python
thread = threading.Thread(
    target=_tagger_batch_coordinator,
    args=(job, file_ids, limit, force, threshold),
    daemon=True,
    name="tagger-mesh-coordinator",
)
thread.start()
```

透過 `job_manager` 防止作業重複啟動，並自動選取未標記的檔案。

---

## 外觀 API 摘要

```python
from core.mesh_inference import get_router, has_mesh, set_router

# 使用範例
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

| 函式 | 說明 |
|---|---|
| `get_router()` | 回傳作用中的 InferenceRouter（未註冊時為 None） |
| `has_mesh()` | 以 bool 回傳 mesh 是否可用 |
| `set_router(router)` | CoworkManager 在啟動/停止時呼叫。啟動時執行永久化載入與策略注入 |

---

## 相關檔案

- `core/mesh_inference/__init__.py` — 外觀模式
- `core/mesh_inference/strategy.py` — DisableAwareStrategy
- `core/mesh_inference/persistence.py` — JSON 永久化
- `core/mesh_inference/dispatch_sync.py` — 同步橋接 + tagger 批次
- `extensions/builtin_lan_cowork/core_impl/inference/router.py` — InferenceRouter + 工作竊取
- `extensions/builtin_lan_cowork/core_impl/inference/state.py` — InferenceState
- `data/mesh_inference_state.json` — 停用覆蓋層永久化位置
