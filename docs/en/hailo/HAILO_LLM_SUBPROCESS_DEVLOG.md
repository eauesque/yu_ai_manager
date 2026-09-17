# Hailo LLM Subprocess GIL Unblock — Implementation Devlog

- **Target**: Resolution of the issue where the Quart event loop freezes due to GIL during HailoRT Python binding cold_load (~71 seconds)
- **Approach**: Isolating LLM chat inference into a subprocess under `core/inference_worker/`
- **spec**: `docs/superpowers/specs/2026-05-17-hailo-llm-subprocess-gil-unblock-design.md`
- **Completed phases**: 0a / 0b / 1 (verified on real hardware)

This document summarizes non-obvious failures and solutions encountered during implementation. The SSE 60-second drop in particular required significant investigation time, so it is recorded here to prevent others from falling into the same trap.

---

## 1. SSE Always Drops at 60 Seconds ("Stream interrupted: network error")

### Symptom

The SSE response from `/ext/hailo-genai/api/chat/send` results in **TCP disconnection at exactly 60 seconds**, regardless of whether cold_load is in progress or tokens are being generated.

- Browser: `Stream interrupted: network error`
- curl: `curl: (18) transfer closed with outstanding read data remaining`
- Access log: `POST ... 1.1 - - 60236944` (status `-`, duration 60.2 seconds)

Even when data is flowing continuously (e.g., 30 tok/s), the connection is dropped — so it is not an idle timeout.

### Isolation

1. **Drops even on local loopback** (`http://127.0.0.1:5000/...` curled on the Pi itself) → not an intermediate network issue, but on the Pi side
2. **Confirmed FIN origin via Wireshark** — FIN sent from 192.168.50.4 (Pi) → 192.168.50.247 (client) at `connection_start + 60.006s`. **Confirmed as Pi-side origin**
3. None of Hypercorn's documented timeouts (`keep_alive_timeout=5s`, `read_timeout=None`, `shutdown_timeout=60s`, etc.) apply to active responses

### Root Cause

**Quart's `RESPONSE_TIMEOUT` setting (default 60 seconds)**

`quart/asgi.py:117`:

```python
timeout = self.app.config["RESPONSE_TIMEOUT"]   # default 60
try:
    await asyncio.wait_for(self._send_response(send, response), timeout=timeout)
except asyncio.TimeoutError:
    pass   # ← after 60s, response sending is aborted → TCP close
```

The default setting does not anticipate long-duration SSE / streaming responses. `RESPONSE_TIMEOUT=60` is intended to prevent runaway non-streaming APIs, but is fatal for SSE.

### Solution

Set a **per-response timeout override** on the Quart `Response` object:

```python
resp = Response(
    sse_generator(),
    mimetype="text/event-stream",
    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
)
resp.timeout = None  # disable RESPONSE_TIMEOUT for SSE
return resp
```

The default of `Response.timeout` is `Ellipsis`, and `app.config["RESPONSE_TIMEOUT"]` is only used when the value is `Ellipsis` (`asgi.py:112-115`). Setting `None` explicitly disables the timeout entirely.

**Fix commit**: `b35ed46cc`

Applied locations:
- `extensions/builtin_hailo_genai/hailo_chat_routes_send.py` — chat SSE
- `extensions/builtin_hailo_genai/hailo_llm_routes.py` — `/api/llm/generate` SSE
- `extensions/builtin_hailo_genai/openai_chat_stream.py` — OpenAI-compatible streaming (×2)

Non-SSE routes are not touched (the 60-second timeout is useful as a protection mechanism there).

### Lessons Learned

- **Quart's `RESPONSE_TIMEOUT` is fatal for SSE**. When adding a new SSE endpoint, always set `resp.timeout = None`.
- When "data is flowing but the connection drops," do not suspect idle timeout. Suspect a fixed max-duration.
- The fastest way to isolate is to **look at the FIN origin IP in Wireshark**. In tcpdump, the filter `tcp[tcpflags] & tcp-fin != 0` also works.

---

## 2. SSE Keepalive During cold_load (Preventive Measure Separate from the 60s Issue)

### Symptom Prevention

Even after disabling `RESPONSE_TIMEOUT`, there is still a separate possibility that **intermediate networks (consumer routers / firewalls / browser stream APIs)** will cut long-duration idle connections. During cold_load's ~71 seconds of silence, intermediate devices may judge the connection as "dead."

### Countermeasure

Wrap `HailoLLMSubprocessClient.stream()` with `stream_with_keepalive()` to send **keepalive data events at 5-second intervals**:

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
                    yield ("ping", None)   # keepalive when silent for 5s
```

When the route receives `("ping", None)`, it yields `data: {"keepalive": true}\n\n`. The client (chat UI) silently ignores events that do not match `d.token` / `d.error` / `d.done`.

### Why `data:` Events Instead of SSE Comments (`: keepalive`)

`: keepalive\n\n` (SSE comments) were tried first, but proved ineffective in the test environment. Switching to `data: {"keepalive":true}` (real data events) resolved it. Although SSE comments are valid per spec, some intermediate devices and browser implementations treat comment lines as "ignorable metadata" and still consider it idle when no real data arrives. Real events are more universally compatible.

**Fix commits**: `d450297c2`, `213b9c962`, `dff60989c`

---

## 3. Worker Subprocess Exits Immediately After Startup in a Loop

### Symptom

`logs/inference_worker.log`:

```
22:46:29 Inference worker started (pid=1612)
22:46:31 Inference worker shutting down   ← normal exit after 2 seconds
22:46:32 Inference worker started (pid=1615)
22:46:34 Inference worker shutting down
...
22:46:41 Worker crashed and max restarts exhausted
```

The worker starts, "cleanly shuts down" after 2 seconds, the parent detects `is_alive=False` → restarts 3 times and gives up; the auto-restart pool is exhausted.

### Root Cause

The main loop of `worker_process.worker_main`:

```python
while True:
    task = queue.get_task(timeout=2.0)
    if task is None or isinstance(task, ShutdownSentinel):   # ← bug
        logger.info("Inference worker shutting down")
        break
```

`get_task(timeout=2.0)` returns `None` when no task is available. This was treated the same as `ShutdownSentinel`, causing a break. The worker waits 2 seconds for a task → fails to get one → returns `None` → misidentified as a "shutdown command" → breaks → parent detects `is_alive=False` → restart loop.

### Solution

```python
if task is None:
    continue                            # timeout → continue polling
if isinstance(task, ShutdownSentinel):
    break                                # break only on explicit shutdown
```

**Fix commit**: `af19f16de`

### Lessons Learned

- `None` from `multiprocessing.Queue.get(timeout=...)` means "timeout." "End of queue" should be expressed using an explicit sentinel like `ShutdownSentinel`. Do not conflate the two.

---

## 4. Worker Cannot Spawn hailo_platform Internal Subprocess Because daemon=True

### Symptom

`Worker crashed` log on first chat in real hardware testing. No stderr capture, so root cause is unknown.

### Root Cause Hypothesis

`bridge.start()`:

```python
self._process = ctx.Process(
    target=worker_main,
    args=(...),
    daemon=True,                    # ← problem
    ...
)
```

`multiprocessing.Process(daemon=True)` auto-kills children when the parent exits, but **daemonic processes cannot spawn their own child processes** (`AssertionError: daemonic processes are not allowed to have children`). This fails if HailoRT internally spawns any helper process or thread.

### Solution

```python
daemon=False
```

Instead, explicitly call `inference_bridge.stop(timeout=5.0)` in `@app.after_serving` for a clean shutdown.

**Fix commit**: `cf49a42a2` (combined with worker logging diagnostics addition)

### Lessons Learned

- Subprocesses using C-extension-based libraries like HailoRT should use `daemon=False`.
- Subprocess cleanup should be done explicitly in `@app.after_serving`.

---

## 5. stderr / logger Output from Spawned Worker Subprocess Is Not Captured

### Symptom

Exception tracebacks inside the worker subprocess **are not preserved anywhere**. stdout/stderr is not routed to the parent process, and logger configuration is not inherited (a characteristic of spawn).

### Solution

Attach a **dedicated logging handler** at the start of `worker_main`:

```python
def _configure_worker_logging() -> None:
    log_path = project_root / "logs" / "inference_worker.log"
    handler = RotatingFileHandler(log_path, maxBytes=2*1024*1024, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] (%(name)s pid=%(process)d) %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
```

Additionally, wrap the entire `worker_main` in `try/except BaseException: logger.critical(traceback.format_exc())` to also capture import-time errors.

**Fix commit**: `cf49a42a2`

### Lessons Learned

- `multiprocessing.get_context("spawn").Process` does not inherit the parent's logging configuration. **Set it up explicitly on the spawned side.**
- Exceptions in daemon threads are also silently swallowed by default (`threading.Thread` default behavior). Add try/except + log to control daemons as well.

---

## 6. bridge.iter_stream Inter-Token Timeout Is Too Short for cold_load

### Symptom

`[WARN] Stream timeout for task ...` appears in the log on first chat, and SSE ends before tokens arrive.

### Root Cause

The `queue.get` timeout in `bridge.iter_stream` was **fixed at 10 seconds**, so the first token does not arrive during cold_load (71 seconds), causing a timeout.

### Solution

Following the policy in spec §3.4:

- `first_token_timeout = 120.0` (cold_load 71s + 50s margin)
- `inter_token_timeout = 30.0` (maximum inter-token interval)
- Switch to short timeout after the first token is received

**Fix commit**: `35d556150`

---

## 7. handler_hailo_llm Skips Prompt Normalisation, Causing HailoRT InvalidOperation

### Symptom

`HailoRTInvalidOperationException` on second and subsequent chat submissions. HailoRT log:

```
[HailoRT] [error] CHECK failed - System role messages can only be provided on the first prompt
```

### Root Cause

The subprocess handler was passing messages raw to `llm.generate(prompt=messages)`, skipping the preprocessing done by the in-process `HailoLLM._prepare_prompt`:

- Flattening of structured content `[{"type":"text","text":"..."}]` → plain string was missing
- Removal of system role when continuing context (turn 2 and beyond) was missing

HailoRT's chat template assumes these two transformations.

### Solution

Share `_normalise_prompt` via import + remove system role when continuing context:

```python
normalised = _normalise_prompt(messages)
if llm_instance.get_context_usage_size() > 0:
    normalised = [m for m in normalised if m.get("role") != "system"]
```

**Fix commit**: `cdd9e26fe`

### Lessons Learned

- When implementing both in-process and subprocess paths, confirm at design time that pre/post-processing done on the in-process side is **applied equally on both paths**. As with the device_manager parent-child state split countermeasure in spec §3.5, factoring into a shared library is preferable.

---

## 8. Cancel During cold_load Is Delayed by a Race Condition

### Symptom (Latent)

During cold_load (71s), the HailoRT C extension holds the GIL, preventing the worker's control daemon thread from running. As a result, `ControlMessage(op="cancel")` from a user disconnect is not processed. If `generate()` is called immediately after cold_load completes, token generation starts for an abandoned task.

### Solution

After `acquire_genai()` completes, wait 50ms → give the control daemon time to process the pending cancel → check `cancel_flags[task_id]` → if True, skip generate():

```python
import time as _time
_time.sleep(0.05)
if cancel_flags.get(task_id, False):
    _emit_terminal(queue, task_id, seq, error="cancelled")
    return InferenceResult(task_id=task_id, status=TaskStatus.CANCELLED, error="cancelled")
```

**Fix commit**: `5fbb02d95`

---

## 9. No Production Code Path Calls inference_worker.start()

### Symptom

Even with `hailo_genai.llm_subprocess: true` in config, sending a chat message results in `RuntimeError("Failed to submit LLM task to worker")`.

### Root Cause

Only `bind_event_loop(loop)` was being executed in `@app.before_serving`; the critical call to `inference_bridge.start(db_path, config)` **did not exist in production**. The worker process was never spawned.

### Solution

Execute `start()` → `bind_event_loop()` in order within `@app.before_serving`, and `stop()` in `@app.after_serving`:

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

**Fix commit**: `9053f2f72`

---

## Complete List of Fixes (Chronological)

| Commit | Description |
|--------|-------------|
| `9053f2f72` | Call inference_bridge.start() in app.before_serving |
| `cf49a42a2` | Worker logging diagnostics + daemon=False + db_path retention for auto-restart |
| `af19f16de` | Fix queue timeout to continue instead of break |
| `35d556150` | iter_stream first_token_timeout 120s, inter_token 30s |
| `d450297c2` | Introduce SSE keepalive comment |
| `cdd9e26fe` | Add prompt normalisation to handler |
| `213b9c962` | Keepalive interval 15s → 5s + diagnostic logs |
| `dff60989c` | Convert keepalive from `: comment` → `data:` event |
| `b35ed46cc` | **Disable Quart RESPONSE_TIMEOUT 60s for SSE (root cause fix)** |
| `5fbb02d95` | Early cancel check after cold_load |

---

## Related Documents

- Main spec: `docs/superpowers/specs/2026-05-17-hailo-llm-subprocess-gil-unblock-design.md`
- Related (REJECTED): `docs/superpowers/specs/2026-05-17-hailo-subprocess-isolation-design.md`
- CMA leak: `docs/ja/hailo/HAILO_CMA_LEAK_HAILORT_5_3_0.md`
- VDevice sharing: `docs/ja/hailo/VDEVICE_SHARING_PATTERN.md`
