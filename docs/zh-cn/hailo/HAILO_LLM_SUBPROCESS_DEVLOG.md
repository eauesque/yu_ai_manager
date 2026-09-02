# Hailo LLM Subprocess GIL Unblock — 实现开发日志

- **对象**：解决 HailoRT Python binding 的 cold_load（约 71 秒）期间，Quart event loop 因 GIL 阻塞而冻结的问题
- **方法**：将 LLM chat 推理隔离至 `core/inference_worker/` 的 subprocess
- **spec**：`docs/superpowers/specs/2026-05-17-hailo-llm-subprocess-gil-unblock-design.md`
- **完成 phase**：0a / 0b / 1（已在实机验证）

本文档整理了实现过程中遭遇的非直观障碍与解决方案。其中 SSE 60 秒断线问题调查耗费最多时间，特此记录以免后人踩入同一陷阱。

---

## 1. SSE 必定在 60 秒后断线（"Stream interrupted: network error"）

### 症状

`/ext/hailo-genai/api/chat/send` 的 SSE 响应，无论 cold_load 是否进行中、token 是否持续生成，均在**恰好 60 秒后发生 TCP 断线**。

- 浏览器：`Stream interrupted: network error`
- curl：`curl: (18) transfer closed with outstanding read data remaining`
- 访问日志：`POST ... 1.1 - - 60236944`（status `-`，duration 60.2 秒）

即使数据持续流出（例如 30 tok/s），连接仍被切断，故非 idle timeout。

### 切分排查

1. **本机 loopback 也会断线**（在 Pi 上以 `http://127.0.0.1:5000/...` curl）→ 非中间网络问题，问题在 Pi 侧
2. **通过 Wireshark 确认 FIN 来源**——192.168.50.4（Pi）→ 192.168.50.247（client）的 FIN 在 `connection_start + 60.006s` 时发出。**确认为 Pi 侧主动发送**
3. Hypercorn 的文档化 timeout（`keep_alive_timeout=5s`、`read_timeout=None`、`shutdown_timeout=60s` 等）均不适用于进行中的响应

### 根本原因

**Quart 的 `RESPONSE_TIMEOUT` 设置（默认 60 秒）**

`quart/asgi.py:117`：

```python
timeout = self.app.config["RESPONSE_TIMEOUT"]   # default 60
try:
    await asyncio.wait_for(self._send_response(send, response), timeout=timeout)
except asyncio.TimeoutError:
    pass   # ← 60 秒后中止响应发送 → TCP close
```

此默认设置并未考虑长时间 SSE / streaming 响应的场景。`RESPONSE_TIMEOUT=60` 本意是防止非流式 API 失控，但对 SSE 而言是致命的。

### 解决方案

对 Quart `Response` 对象设置**每个响应独立的 timeout 覆盖**：

```python
resp = Response(
    sse_generator(),
    mimetype="text/event-stream",
    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
)
resp.timeout = None  # disable RESPONSE_TIMEOUT for SSE
return resp
```

`Response.timeout` 的默认值为 `Ellipsis`，仅在值为 `Ellipsis` 时才会使用 `app.config["RESPONSE_TIMEOUT"]`（`asgi.py:112-115`）。明确设为 `None` 即可禁用 timeout。

**修正 commit**：`b35ed46cc`

应用位置：
- `extensions/builtin_hailo_genai/hailo_chat_routes_send.py` — chat SSE
- `extensions/builtin_hailo_genai/hailo_llm_routes.py` — `/api/llm/generate` SSE
- `extensions/builtin_hailo_genai/openai_chat_stream.py` — OpenAI 兼容流式输出（×2）

非 SSE 路由不做更改（60 秒 timeout 在此仍有保护作用）。

### 教训

- **Quart 的 `RESPONSE_TIMEOUT` 对 SSE 是致命的**。新增 SSE endpoint 时务必设置 `resp.timeout = None`。
- 「数据持续流出却断线」时，不要怀疑 idle timeout，应怀疑固定的最大时长限制。
- 最快的排查方式是**用 Wireshark 查看 FIN 的来源 IP**。使用 tcpdump 时也可用 `tcp[tcpflags] & tcp-fin != 0` 过滤。

---

## 2. cold_load 期间的 SSE keepalive（60 秒问题以外的预防措施）

### 症状预防

即使禁用了 `RESPONSE_TIMEOUT`，**中间网络（consumer router／防火墙／浏览器 stream API）**仍可能主动切断长时间空闲的连接，这是另一个独立的风险。cold_load 期间约 71 秒不发送任何数据，可能被中间设备判定为「无效」连接。

### 对策

以 `stream_with_keepalive()` 包装 `HailoLLMSubprocessClient.stream()`，以**每 5 秒发送一次 keepalive 数据事件**：

```python
async def stream_with_keepalive(async_iter, ping_interval: float = 5.0):
    ...
    while True:
        next_task = asyncio.ensure_future(it.__anext__())
        try:
            while True:
                try:
                    value = await asyncio.wait_for(asyncio.shield(next_task), timeout=ping_interval)
                    yield ("token", value)
                    break
                except asyncio.TimeoutError:
                    yield ("ping", None)   # 5 秒无数据时发送 keepalive
```

route 侧收到 `("ping", None)` 时，yield `data: {"keepalive": true}\n\n`。客户端（chat UI）对不符合 `d.token` / `d.error` / `d.done` 的事件采静默忽略。

### 使用 `data:` event 而非 SSE comment（`: keepalive`）的原因

起初尝试使用 `: keepalive\n\n`（SSE comment），但在测试环境中无效。改为 `data: {"keepalive":true}`（真实数据事件）后问题解决。虽然 SSE 规范允许 comment，但部分中间设备与浏览器实现将 comment 视为「可忽略的 metadata」，在没有真实数据时仍判断为 idle。真实事件的兼容性更广。

**修正 commits**：`d450297c2`、`213b9c962`、`dff60989c`

---

## 3. Worker Subprocess 启动后立即进入反复退出的循环

### 症状

`logs/inference_worker.log`：

```
22:46:29 Inference worker started (pid=1612)
22:46:31 Inference worker shutting down   ← 2 秒后正常退出
22:46:32 Inference worker started (pid=1615)
22:46:34 Inference worker shutting down
...
22:46:41 Worker crashed and max restarts exhausted
```

worker 启动后 2 秒「正常 shutdown」，父进程检测到 `is_alive=False` → 重启 3 次后放弃，auto-restart pool 耗尽。

### 根本原因

`worker_process.worker_main` 的主循环：

```python
while True:
    task = queue.get_task(timeout=2.0)
    if task is None or isinstance(task, ShutdownSentinel):   # ← bug
        logger.info("Inference worker shutting down")
        break
```

`get_task(timeout=2.0)` 在没有 task 时返回 None。这被误与 `ShutdownSentinel` 同等处理而 break。worker 启动后等待 2 秒 → 获取失败返回 None → 误认为「shutdown 命令」→ break → 父进程检测到 `is_alive=False` → 重启循环。

### 解决方案

```python
if task is None:
    continue                            # timeout 则继续轮询
if isinstance(task, ShutdownSentinel):
    break                                # 仅明确 shutdown 时 break
```

**修正 commit**：`af19f16de`

### 教训

- `multiprocessing.Queue.get(timeout=...)` 返回 `None` 代表「timeout」，而非「queue 结束」。「queue 结束」应以 `ShutdownSentinel` 等明确的 sentinel 表示。两者不可混淆。

---

## 4. Worker 因 daemon=True 导致 hailo_platform 无法在内部启动 Subprocess

### 症状

实机首次 chat 时出现 `Worker crashed` 日志。因未捕捉 stderr，原因不明。

### 根本原因假设

`bridge.start()`：

```python
self._process = ctx.Process(
    target=worker_main,
    args=(...),
    daemon=True,                    # ← 问题所在
    ...
)
```

`multiprocessing.Process(daemon=True)` 会在父进程退出时自动 kill 子进程，但**daemonic process 无法自行 spawn 子进程**（`AssertionError: daemonic processes are not allowed to have children`）。若 HailoRT 内部需要启动任何 helper process／thread，此时便会崩溃。

### 解决方案

```python
daemon=False
```

改在 `@app.after_serving` 中明确调用 `inference_bridge.stop(timeout=5.0)` 以进行干净的关机。

**修正 commit**：`cf49a42a2`（与 worker logging diagnostics 新增一并提交）

### 教训

- 使用 HailoRT 等以 C 扩展为基础的库的 subprocess，应设置 `daemon=False`。
- Subprocess 的清理应在 `@app.after_serving` 中明确执行。

---

## 5. 被 Spawn 的 Worker Subprocess 的 stderr／logger 输出无法被捕捉

### 症状

worker subprocess 内的异常 traceback **不会保留在任何地方**。stdout/stderr 不会路由至父进程，logger 配置也不会被继承（spawn 的特性）。

### 解决方案

在 `worker_main` 开头附加**专用的 logging handler**：

```python
def _configure_worker_logging() -> None:
    log_path = project_root / "logs" / "inference_worker.log"
    handler = RotatingFileHandler(log_path, maxBytes=2*1024*1024, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] (%(name)s pid=%(process)d) %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
```

此外，以 `try/except BaseException: logger.critical(traceback.format_exc())` 包装整个 `worker_main`，以捕捉 import 时的错误。

**修正 commit**：`cf49a42a2`

### 教训

- `multiprocessing.get_context("spawn").Process` 不会继承父进程的 logging 配置。**必须在被 spawn 的一侧明确设置**。
- daemon thread 的异常默认也会被静默吞掉（`threading.Thread` 默认行为）。control daemon 也应加入 try/except + log。

---

## 6. bridge.iter_stream 的 inter-token timeout 对 cold_load 而言过短

### 症状

首次 chat 时日志出现 `[WARN] Stream timeout for task ...`，在 token 到达前 SSE 便结束。

### 根本原因

`bridge.iter_stream` 的 queue.get timeout **固定为 10 秒**，因此在 cold_load（71 秒）期间 first token 尚未到达便已 timeout。

### 解决方案

依照 spec §3.4 的方针：

- `first_token_timeout = 120.0`（cold_load 71s + 50s 余量）
- `inter_token_timeout = 30.0`（token 间最大间隔）
- 收到第一个 token 后切换至较短的 timeout

**修正 commit**：`35d556150`

---

## 7. handler_hailo_llm 跳过 Prompt 规范化导致 HailoRT InvalidOperation

### 症状

第二次及后续 chat 发送时出现 `HailoRTInvalidOperationException`。HailoRT 日志：

```
[HailoRT] [error] CHECK failed - System role messages can only be provided on the first prompt
```

### 根本原因

subprocess handler 直接将 messages 原始传给 `llm.generate(prompt=messages)`，跳过了 in-process `HailoLLM._prepare_prompt` 的前处理：

- 结构化内容 `[{"type":"text","text":"..."}]` → 纯字符串的扁平化处理缺失
- 继续上下文时（第 2 轮起）的 system role 移除缺失

HailoRT 的 chat template 以这两项转换为前提。

### 解决方案

通过共用 import 使用 `_normalise_prompt` + 继续上下文时移除 system role：

```python
normalised = _normalise_prompt(messages)
if llm_instance.get_context_usage_size() > 0:
    normalised = [m for m in normalised if m.get("role") != "system"]
```

**修正 commit**：`cdd9e26fe`

### 教训

- 同时实现 in-process 与 subprocess 两条路径时，在设计阶段即确认 in-process 侧进行的 pre/post-processing **两条路径均同等应用**。如同 spec §3.5 的 device_manager 父子状态分裂对策，建议抽取为共用库。

---

## 8. cold_load 期间的 cancel 因竞态条件而延迟

### 症状（潜在）

cold_load（71 秒）期间，HailoRT C 扩展持有 GIL，worker 的 control daemon thread 无法运行，因此用户断线时的 `ControlMessage(op="cancel")` 无法被处理。cold_load 完成后立即调用 `generate()` 时，会为已被放弃的 task 开始生成 token。

### 解决方案

`acquire_genai()` 完成后等待 50ms → 给予 control daemon 处理 pending cancel 的机会 → 检查 `cancel_flags[task_id]` → 若为 True 则跳过 generate()：

```python
import time as _time
_time.sleep(0.05)
if cancel_flags.get(task_id, False):
    _emit_terminal(queue, task_id, seq, error="cancelled")
    return InferenceResult(task_id=task_id, status=TaskStatus.CANCELLED, error="cancelled")
```

**修正 commit**：`5fbb02d95`

---

## 9. Production 中不存在调用 inference_worker.start() 的代码路径

### 症状

即使在 config 设置 `hailo_genai.llm_subprocess: true`，chat 发送时仍出现 `RuntimeError("Failed to submit LLM task to worker")`。

### 根本原因

`@app.before_serving` 中只执行了 `bind_event_loop(loop)`，关键的 `inference_bridge.start(db_path, config)` 调用在 production 中**根本不存在**。worker process 永远不会被 spawn。

### 解决方案

在 `@app.before_serving` 中依序执行 `start()` → `bind_event_loop()`，在 `@app.after_serving` 中执行 `stop()`：

```python
@app.before_serving
async def start_inference_bridge() -> None:
    from core.inference_worker.bridge import inference_bridge
    from core.services_core.db_state import get_db_path
    inference_bridge.start(str(get_db_path()), config)
    inference_bridge.bind_event_loop(asyncio.get_running_loop())

@app.after_serving
async def stop_inference_bridge() -> None:
    inference_bridge.stop(timeout=5.0)
```

**修正 commit**：`9053f2f72`

---

## 完整修正清单（按时间顺序）

| Commit | 内容 |
|--------|------|
| `9053f2f72` | 在 app.before_serving 中调用 inference_bridge.start() |
| `cf49a42a2` | worker logging diagnostics + daemon=False + auto-restart 保留 db_path |
| `af19f16de` | 修正 queue timeout 为 continue |
| `35d556150` | iter_stream first_token_timeout 120s，inter_token 30s |
| `d450297c2` | 引入 SSE keepalive comment |
| `cdd9e26fe` | 在 handler 加入 prompt normalisation |
| `213b9c962` | keepalive 间隔 15s → 5s + 诊断日志 |
| `dff60989c` | keepalive 从 `: comment` 改为 `data:` event |
| `b35ed46cc` | **在 SSE 禁用 Quart RESPONSE_TIMEOUT 60s（根本原因修正）** |
| `5fbb02d95` | cold_load 后的提前 cancel 检查 |

---

## 相关文档

- spec 本体：`docs/superpowers/specs/2026-05-17-hailo-llm-subprocess-gil-unblock-design.md`
- 相关（REJECTED）：`docs/superpowers/specs/2026-05-17-hailo-subprocess-isolation-design.md`
- CMA leak：`docs/ja/hailo/HAILO_CMA_LEAK_HAILORT_5_3_0.md`
- VDevice 共享：`docs/ja/hailo/VDEVICE_SHARING_PATTERN.md`
