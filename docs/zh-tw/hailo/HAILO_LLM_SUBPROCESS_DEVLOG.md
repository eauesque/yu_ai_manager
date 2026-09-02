# Hailo LLM Subprocess GIL Unblock — 實作開發日誌

- **對象**：解決 HailoRT Python binding 的 cold_load（約 71 秒）期間，Quart event loop 因 GIL 阻塞而凍結的問題
- **方法**：將 LLM chat 推論隔離至 `core/inference_worker/` 的 subprocess
- **spec**：`docs/superpowers/specs/2026-05-17-hailo-llm-subprocess-gil-unblock-design.md`
- **完成 phase**：0a / 0b / 1（已於實機驗證）

本文件整理了實作過程中遭遇的非直觀障礙與解決方案。其中 SSE 60 秒斷線問題調查耗費最多時間，特此記錄以免後人踩入同一陷阱。

---

## 1. SSE 必定在 60 秒後斷線（"Stream interrupted: network error"）

### 症狀

`/ext/hailo-genai/api/chat/send` 的 SSE 回應，無論 cold_load 是否進行中、token 是否持續生成，皆在**恰好 60 秒後發生 TCP 斷線**。

- 瀏覽器：`Stream interrupted: network error`
- curl：`curl: (18) transfer closed with outstanding read data remaining`
- 存取日誌：`POST ... 1.1 - - 60236944`（status `-`，duration 60.2 秒）

即使資料持續流出（例如 30 tok/s），連線仍被切斷，故非 idle timeout。

### 切分排查

1. **本機 loopback 也會斷線**（在 Pi 上以 `http://127.0.0.1:5000/...` curl）→ 非中間網路問題，問題在 Pi 側
2. **透過 Wireshark 確認 FIN 來源**——192.168.50.4（Pi）→ 192.168.50.247（client）的 FIN 在 `connection_start + 60.006s` 時送出。**確認為 Pi 側主動發送**
3. Hypercorn 的文件化 timeout（`keep_alive_timeout=5s`、`read_timeout=None`、`shutdown_timeout=60s` 等）均不適用於進行中的回應

### 根本原因

**Quart 的 `RESPONSE_TIMEOUT` 設定（預設 60 秒）**

`quart/asgi.py:117`：

```python
timeout = self.app.config["RESPONSE_TIMEOUT"]   # default 60
try:
    await asyncio.wait_for(self._send_response(send, response), timeout=timeout)
except asyncio.TimeoutError:
    pass   # ← 60 秒後中止回應發送 → TCP close
```

此預設設定並未考慮長時間 SSE / streaming 回應的情境。`RESPONSE_TIMEOUT=60` 本意是防止非串流 API 失控，但對 SSE 而言是致命的。

### 解決方案

對 Quart `Response` 物件設定**每個回應獨立的 timeout 覆寫**：

```python
resp = Response(
    sse_generator(),
    mimetype="text/event-stream",
    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
)
resp.timeout = None  # disable RESPONSE_TIMEOUT for SSE
return resp
```

`Response.timeout` 的預設值為 `Ellipsis`，僅在值為 `Ellipsis` 時才會使用 `app.config["RESPONSE_TIMEOUT"]`（`asgi.py:112-115`）。明確設為 `None` 即可停用 timeout。

**修正 commit**：`b35ed46cc`

套用位置：
- `extensions/builtin_hailo_genai/hailo_chat_routes_send.py` — chat SSE
- `extensions/builtin_hailo_genai/hailo_llm_routes.py` — `/api/llm/generate` SSE
- `extensions/builtin_hailo_genai/openai_chat_stream.py` — OpenAI 相容串流（×2）

非 SSE 路由不做更動（60 秒 timeout 在此仍有保護作用）。

### 教訓

- **Quart 的 `RESPONSE_TIMEOUT` 對 SSE 是致命的**。新增 SSE endpoint 時務必設定 `resp.timeout = None`。
- 「資料持續流出卻斷線」時，不要懷疑 idle timeout，應懷疑固定的最大時長限制。
- 最快的排查方式是**用 Wireshark 查看 FIN 的來源 IP**。使用 tcpdump 時也可用 `tcp[tcpflags] & tcp-fin != 0` 過濾。

---

## 2. cold_load 期間的 SSE keepalive（60 秒問題以外的預防措施）

### 症狀預防

即使停用了 `RESPONSE_TIMEOUT`，**中間網路（consumer router／防火牆／瀏覽器 stream API）**仍可能主動切斷長時間閒置的連線，這是另一個獨立的風險。cold_load 期間約 71 秒不發送任何資料，可能被中間設備判定為「無效」連線。

### 對策

以 `stream_with_keepalive()` 包裝 `HailoLLMSubprocessClient.stream()`，以**每 5 秒發送一次 keepalive 資料事件**：

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
                    yield ("ping", None)   # 5 秒無資料時送出 keepalive
```

route 側收到 `("ping", None)` 時，yield `data: {"keepalive": true}\n\n`。客戶端（chat UI）對不符合 `d.token` / `d.error` / `d.done` 的事件採靜默忽略。

### 使用 `data:` event 而非 SSE comment（`: keepalive`）的原因

起初嘗試使用 `: keepalive\n\n`（SSE comment），但在測試環境中無效。改為 `data: {"keepalive":true}`（真實資料事件）後問題解決。雖然 SSE 規範允許 comment，但部分中間設備與瀏覽器實作將 comment 視為「可忽略的 metadata」，在沒有真實資料時仍判斷為 idle。真實事件的相容性更廣。

**修正 commits**：`d450297c2`、`213b9c962`、`dff60989c`

---

## 3. Worker Subprocess 啟動後立即進入反覆退出的循環

### 症狀

`logs/inference_worker.log`：

```
22:46:29 Inference worker started (pid=1612)
22:46:31 Inference worker shutting down   ← 2 秒後正常退出
22:46:32 Inference worker started (pid=1615)
22:46:34 Inference worker shutting down
...
22:46:41 Worker crashed and max restarts exhausted
```

worker 啟動後 2 秒「正常 shutdown」，父程序偵測 `is_alive=False` → 重啟 3 次後放棄，auto-restart pool 耗盡。

### 根本原因

`worker_process.worker_main` 的主循環：

```python
while True:
    task = queue.get_task(timeout=2.0)
    if task is None or isinstance(task, ShutdownSentinel):   # ← bug
        logger.info("Inference worker shutting down")
        break
```

`get_task(timeout=2.0)` 在沒有 task 時回傳 None。這被誤與 `ShutdownSentinel` 同等處理而 break。worker 啟動後等待 2 秒 → 取得失敗回傳 None → 誤認為「shutdown 命令」→ break → 父程序偵測 `is_alive=False` → 重啟循環。

### 解決方案

```python
if task is None:
    continue                            # timeout 則繼續輪詢
if isinstance(task, ShutdownSentinel):
    break                                # 僅明確 shutdown 時 break
```

**修正 commit**：`af19f16de`

### 教訓

- `multiprocessing.Queue.get(timeout=...)` 回傳 `None` 代表「timeout」，而非「queue 結束」。「queue 結束」應以 `ShutdownSentinel` 等明確的 sentinel 表示。兩者不可混淆。

---

## 4. Worker 因 daemon=True 導致 hailo_platform 無法在內部啟動 Subprocess

### 症狀

實機首次 chat 時出現 `Worker crashed` 日誌。因未捕捉 stderr，原因不明。

### 根本原因假設

`bridge.start()`：

```python
self._process = ctx.Process(
    target=worker_main,
    args=(...),
    daemon=True,                    # ← 問題所在
    ...
)
```

`multiprocessing.Process(daemon=True)` 會在父程序退出時自動 kill 子程序，但**daemonic process 無法自行 spawn 子程序**（`AssertionError: daemonic processes are not allowed to have children`）。若 HailoRT 內部需要啟動任何 helper process／thread，此時便會崩潰。

### 解決方案

```python
daemon=False
```

改在 `@app.after_serving` 中明確呼叫 `inference_bridge.stop(timeout=5.0)` 以進行乾淨的關機。

**修正 commit**：`cf49a42a2`（與 worker logging diagnostics 新增一併提交）

### 教訓

- 使用 HailoRT 等以 C 擴充為基礎之函式庫的 subprocess，應設定 `daemon=False`。
- Subprocess 的清理應在 `@app.after_serving` 中明確執行。

---

## 5. 被 Spawn 的 Worker Subprocess 的 stderr／logger 輸出無法被捕捉

### 症狀

worker subprocess 內的例外 traceback **不會保留在任何地方**。stdout/stderr 不會路由至父程序，logger 設定也不會被繼承（spawn 的特性）。

### 解決方案

在 `worker_main` 開頭附加**專用的 logging handler**：

```python
def _configure_worker_logging() -> None:
    log_path = project_root / "logs" / "inference_worker.log"
    handler = RotatingFileHandler(log_path, maxBytes=2*1024*1024, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] (%(name)s pid=%(process)d) %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
```

此外，以 `try/except BaseException: logger.critical(traceback.format_exc())` 包裝整個 `worker_main`，以補捉 import 時的錯誤。

**修正 commit**：`cf49a42a2`

### 教訓

- `multiprocessing.get_context("spawn").Process` 不會繼承父程序的 logging 設定。**必須在被 spawn 的一側明確設定**。
- daemon thread 的例外預設也會被靜默吞掉（`threading.Thread` 預設行為）。control daemon 也應加入 try/except + log。

---

## 6. bridge.iter_stream 的 inter-token timeout 對 cold_load 而言過短

### 症狀

首次 chat 時日誌出現 `[WARN] Stream timeout for task ...`，在 token 抵達前 SSE 便結束。

### 根本原因

`bridge.iter_stream` 的 queue.get timeout **固定為 10 秒**，因此在 cold_load（71 秒）期間 first token 尚未抵達便已 timeout。

### 解決方案

依照 spec §3.4 的方針：

- `first_token_timeout = 120.0`（cold_load 71s + 50s 餘裕）
- `inter_token_timeout = 30.0`（token 間最大間隔）
- 收到第一個 token 後切換至較短的 timeout

**修正 commit**：`35d556150`

---

## 7. handler_hailo_llm 跳過 Prompt 正規化導致 HailoRT InvalidOperation

### 症狀

第二次及後續 chat 送出時出現 `HailoRTInvalidOperationException`。HailoRT 日誌：

```
[HailoRT] [error] CHECK failed - System role messages can only be provided on the first prompt
```

### 根本原因

subprocess handler 直接將 messages 原始傳給 `llm.generate(prompt=messages)`，跳過了 in-process `HailoLLM._prepare_prompt` 的前處理：

- 結構化內容 `[{"type":"text","text":"..."}]` → 純字串的扁平化處理缺失
- 繼續上下文時（第 2 輪起）的 system role 移除缺失

HailoRT 的 chat template 以這兩項轉換為前提。

### 解決方案

透過共用 import 使用 `_normalise_prompt` + 繼續上下文時移除 system role：

```python
normalised = _normalise_prompt(messages)
if llm_instance.get_context_usage_size() > 0:
    normalised = [m for m in normalised if m.get("role") != "system"]
```

**修正 commit**：`cdd9e26fe`

### 教訓

- 同時實作 in-process 與 subprocess 兩條路徑時，在設計階段即確認 in-process 側進行的 pre/post-processing **兩條路徑均同等套用**。如同 spec §3.5 的 device_manager 父子狀態分裂對策，建議抽出為共用函式庫。

---

## 8. cold_load 期間的 cancel 因競態條件而延遲

### 症狀（潛在）

cold_load（71 秒）期間，HailoRT C 擴充持有 GIL，worker 的 control daemon thread 無法執行，因此使用者斷線時的 `ControlMessage(op="cancel")` 無法被處理。cold_load 完成後立即呼叫 `generate()` 時，會為已被放棄的 task 開始生成 token。

### 解決方案

`acquire_genai()` 完成後等待 50ms → 給予 control daemon 處理 pending cancel 的機會 → 檢查 `cancel_flags[task_id]` → 若為 True 則跳過 generate()：

```python
import time as _time
_time.sleep(0.05)
if cancel_flags.get(task_id, False):
    _emit_terminal(queue, task_id, seq, error="cancelled")
    return InferenceResult(task_id=task_id, status=TaskStatus.CANCELLED, error="cancelled")
```

**修正 commit**：`5fbb02d95`

---

## 9. Production 中不存在呼叫 inference_worker.start() 的程式碼路徑

### 症狀

即使在 config 設定 `hailo_genai.llm_subprocess: true`，chat 送出時仍出現 `RuntimeError("Failed to submit LLM task to worker")`。

### 根本原因

`@app.before_serving` 中只執行了 `bind_event_loop(loop)`，關鍵的 `inference_bridge.start(db_path, config)` 呼叫在 production 中**根本不存在**。worker process 永遠不會被 spawn。

### 解決方案

在 `@app.before_serving` 中依序執行 `start()` → `bind_event_loop()`，在 `@app.after_serving` 中執行 `stop()`：

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

## 完整修正清單（依時間順序）

| Commit | 內容 |
|--------|------|
| `9053f2f72` | 在 app.before_serving 中呼叫 inference_bridge.start() |
| `cf49a42a2` | worker logging diagnostics + daemon=False + auto-restart 保留 db_path |
| `af19f16de` | 修正 queue timeout 為 continue |
| `35d556150` | iter_stream first_token_timeout 120s，inter_token 30s |
| `d450297c2` | 導入 SSE keepalive comment |
| `cdd9e26fe` | 在 handler 加入 prompt normalisation |
| `213b9c962` | keepalive 間隔 15s → 5s + 診斷日誌 |
| `dff60989c` | keepalive 從 `: comment` 改為 `data:` event |
| `b35ed46cc` | **在 SSE 停用 Quart RESPONSE_TIMEOUT 60s（根本原因修正）** |
| `5fbb02d95` | cold_load 後的提前 cancel 檢查 |

---

## 相關文件

- spec 本體：`docs/superpowers/specs/2026-05-17-hailo-llm-subprocess-gil-unblock-design.md`
- 相關（REJECTED）：`docs/superpowers/specs/2026-05-17-hailo-subprocess-isolation-design.md`
- CMA leak：`docs/ja/hailo/HAILO_CMA_LEAK_HAILORT_5_3_0.md`
- VDevice 共享：`docs/ja/hailo/VDEVICE_SHARING_PATTERN.md`
