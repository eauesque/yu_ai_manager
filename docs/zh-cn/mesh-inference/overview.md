# 网状推理架构

> 适用版本: v4.67.0 及以上

## 概述

网状推理系统是局域网上多个 yu_ai_manager 节点协同进行推理任务（tagger / clip / yolo / whisper）分布式处理的机制。结合 mDNS 自动发现、基于 asyncio.Queue 的工作窃取以及按节点的禁用过滤，实现零配置水平扩展。

---

## 整体架构

```
┌─────────────────────────────────────────────────┐
│                 CoworkManager                   │
│  启动时创建 InferenceRouter                     │
│  并注册到 core.mesh_inference.set_router()      │
└────────────────────┬────────────────────────────┘
                     │
          ┌──────────▼──────────┐
          │   InferenceRouter   │  extensions/builtin_lan_cowork/
          │                     │  core_impl/inference/router.py
          │  _local_peer        │
          │  _registry ─────────┼──► PeerRegistry（局域网节点列表）
          │  _strategy ─────────┼──► DisableAwareStrategy
          └──────────┬──────────┘
                     │ dispatch_inference()
          ┌──────────▼──────────┐
          │   asyncio.Queue     │  工作窃取队列
          │   item, item, ...   │
          └──┬───────────┬──────┘
             │           │
       ┌─────▼──┐   ┌────▼────┐
       │ peer A │   │ peer B  │   （并行 worker）
       │(local) │   │(remote) │
       └────────┘   └─────────┘
```

### 组件职责

| 组件 | 位置 | 职责 |
|---|---|---|
| `core.mesh_inference` | `core/mesh_inference/__init__.py` | 门面: get_router / set_router |
| `InferenceRouter` | `extensions/builtin_lan_cowork/…/router.py` | 批量分发与工作窃取 |
| `PeerRegistry` | `extensions/builtin_lan_cowork/…/registry.py` | 节点管理与在线判定 |
| `DisableAwareStrategy` | `core/mesh_inference/strategy.py` | per-peer-per-type 禁用过滤 |
| `InferenceState` | `extensions/builtin_lan_cowork/…/state.py` | 本地引擎引用 |
| `dispatch_sync` | `core/mesh_inference/dispatch_sync.py` | async→thread 桥接 |
| `persistence` | `core/mesh_inference/persistence.py` | JSON 持久化 |

---

## 节点自动发现（mDNS Phase B）

在局域网上广播 `_yu-ai._tcp.local.` 服务并浏览同一服务，实现相互发现。

```
node A                               node B
  │  ── mDNS advertise ──►           │
  │  ◄── mDNS browse ────            │
  │                                  │
  │  ── GET /api/mdns/identity ──►   │
  │  ◄── {node_id, capabilities} ─── │
  │                                  │
  │  注册到 PeerRegistry              │
```

发现流程详情：
1. `LlmRouterMdnsBridge` 接收 mDNS 事件
2. 通过 `/api/mdns/identity` HTTP 验证确认节点是否为真正的 yu_ai_manager
3. 验证成功后将节点添加到 `PeerRegistry`
4. `InferenceState.get_inference_types()` 返回的类型列表反映到 `PeerInfo.inference_types`

---

## 推理类型与后端

`InferenceState.get_inference_types()` 返回的字符串设置到 `PeerInfo.inference_types`，作为路由的依据。

| 推理类型 | 后端 | 用途 |
|---|---|---|
| `tagger` | ONNX (WD14 等) / Hailo NPU | 图像标签 |
| `clip` | ONNX / Hailo / 远程 | 图像嵌入向量 |
| `yolo` | ONNX / Hailo | 物体检测 |
| `whisper` | faster-whisper / 远程 | 语音转文字 |
| `hailo` | Hailo-10H vdevice | Hailo 设备直接访问 |
| `llm` | OpenAI-compat / Ollama | LLM 推理 |

引擎为 `None` 的类型不会包含在 `get_inference_types()` 的列表中，因此不会路由到该节点。

---

## 工作窃取算法

```python
# router.py（概要）
queue: asyncio.Queue = asyncio.Queue()
for item in items:
    queue.put_nowait(item)

async def _worker(peer: PeerInfo) -> None:
    while True:
        batch = []
        for _ in range(batch_size):
            batch.append(queue.get_nowait())   # QueueEmpty 时退出
        if not batch:
            return
        results = await worker_fn(peer, batch)
        result_fn(results)

tasks = [asyncio.create_task(_worker(p)) for p in peers]
await asyncio.gather(*tasks)
```

**特性：**
- 每个节点启动 1 个 worker（通过 `asyncio.create_task()`）
- 以 `batch_size` 为单位从共享队列取出（`get_nowait()` 非阻塞）
- 速度快的节点消费更多队列任务 → 自然的负载均衡
- 通过 `stats_lock` 对 `processed` / `errors` 进行互斥更新

---

## DisableAwareStrategy（v4.67.0）

继承 `BatchInferenceStrategy`，通过 `MeshInferenceState` 的禁用覆盖层进行额外过滤。

```python
class DisableAwareStrategy(BatchInferenceStrategy):
    def select_peers(self, inference_type, peers, mode="parallel"):
        base = super().select_peers(inference_type, peers, mode)
        return [
            p for p in base
            if not self._state.is_disabled(p.peer_id, inference_type)
        ]
```

- `super().select_peers()` 应用在线和 capability 过滤
- 然后排除 `(peer_id, inference_type)` 对已被禁用的条目
- 用于从 WebUI 暂停特定节点的特定类型

---

## 持久化: data/mesh_inference_state.json

通过原子写入持久化禁用覆盖层。

```json
{
  "version": 1,
  "disabled": {
    "<peer_id>": ["tagger", "clip"]
  }
}
```

- `persistence.save_state()` 先写入 `.tmp` 文件，然后通过 `os.replace()` 原子替换
- `persistence.load_state()` 在文件不存在、JSON 损坏、版本不匹配时均回退到空状态
- `set_router()` 时仅加载一次（`_load_persistence_once()`），注入到 `DisableAwareStrategy`

---

## 故障转移：节点故障时的自动恢复

```
dispatch_inference() 调用
    ↓
_get_available_peers() → PeerRegistry.list_online()
    ↓
节点为 0 时:
    输出警告日志并返回 {"status":"ok","processed":0,"errors":N}
    ↓
调用方检测到 errors>0 后回退到本地处理
```

- `PeerRegistry` 在节点存活检查失败时转为 `status="offline"`
- `BatchInferenceStrategy.select_peers()` 仅返回 `status=="online"` 的节点
- 本地节点始终在 `all_peers` 的最前面，因此即使所有远程节点都失败也会自动回退到本地处理

---

## dispatch_sync：同步调用桥接

从后台线程（无事件循环）调用 `InferenceRouter` 的桥接。

```python
# core/mesh_inference/dispatch_sync.py
def dispatch_inference_sync(router, inference_type, items, **kwargs):
    async def _run():
        return await router.dispatch_inference(inference_type, items, **kwargs)
    return asyncio.run(_run())
```

**注意：** 不可从现有的 `asyncio` 循环内使用。在协程中请直接使用 `await router.dispatch_inference(...)`。

### tagger 批处理协调器

`run_tagger_batch()` 是使用 `dispatch_inference_sync` 的高级工具，在后台线程中启动标签任务。

```python
thread = threading.Thread(
    target=_tagger_batch_coordinator,
    args=(job, file_ids, limit, force, threshold),
    daemon=True,
    name="tagger-mesh-coordinator",
)
thread.start()
```

通过 `job_manager` 防止任务重复启动，自动选择未标记文件。

---

## 门面 API 概要

```python
from core.mesh_inference import get_router, has_mesh, set_router

# 使用示例
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

| 函数 | 说明 |
|---|---|
| `get_router()` | 返回活跃的 InferenceRouter（未注册时返回 None）|
| `has_mesh()` | 以 bool 返回 mesh 是否可用 |
| `set_router(router)` | CoworkManager 在启动/停止时调用。启动时执行持久化加载和策略注入 |

---

## 相关文件

- `core/mesh_inference/__init__.py` — 门面
- `core/mesh_inference/strategy.py` — DisableAwareStrategy
- `core/mesh_inference/persistence.py` — JSON 持久化
- `core/mesh_inference/dispatch_sync.py` — 同步桥接 + tagger 批处理
- `extensions/builtin_lan_cowork/core_impl/inference/router.py` — InferenceRouter + 工作窃取
- `extensions/builtin_lan_cowork/core_impl/inference/state.py` — InferenceState
- `data/mesh_inference_state.json` — 禁用覆盖层持久化位置
