# Hailo LLM Subprocess GIL Unblock — 구현 개발 일지

- **대상**: HailoRT Python binding의 cold_load(약 71초) 동안 Quart event loop가 GIL에 의해 차단되어 멈추는 문제 해결
- **방법**: LLM chat 추론을 `core/inference_worker/`의 subprocess로 격리
- **spec**: `docs/superpowers/specs/2026-05-17-hailo-llm-subprocess-gil-unblock-design.md`
- **완료 phase**: 0a / 0b / 1 (실기 검증 완료)

본 문서는 구현 과정에서 마주친 비직관적인 장애와 해결책을 정리한다. 특히 SSE 60초 드롭은 조사에 시간이 많이 소요되었으므로, 후속 작업자가 같은 함정에 빠지지 않도록 기록한다.

---

## 1. SSE가 60초에 반드시 끊어짐 ("Stream interrupted: network error")

### 증상

`/ext/hailo-genai/api/chat/send`의 SSE 응답이 cold_load 진행 중·토큰 생성 중과 무관하게 **정확히 60초에 TCP 연결 끊김** 발생.

- 브라우저: `Stream interrupted: network error`
- curl: `curl: (18) transfer closed with outstanding read data remaining`
- 액세스 로그: `POST ... 1.1 - - 60236944` (status `-`, duration 60.2초)

데이터가 연속으로 흐르고 있어도(예: 30 tok/s) 끊어지므로 idle timeout이 아님.

### 절리

1. **로컬 loopback에서도 끊어짐** (Pi에서 `http://127.0.0.1:5000/...`을 curl) → 중간 네트워크가 아니라 Pi 측 문제
2. **Wireshark로 FIN 발신 확인** — 192.168.50.4(Pi) → 192.168.50.247(client)의 FIN이 `connection_start + 60.006s`에 전송. **Pi 측 발신으로 확정**
3. Hypercorn의 문서화된 timeout(`keep_alive_timeout=5s`, `read_timeout=None`, `shutdown_timeout=60s` 등)은 어떤 것도 활성 응답에 적용되지 않음

### 근본 원인

**Quart의 `RESPONSE_TIMEOUT` 설정 (기본값 60초)**

`quart/asgi.py:117`:

```python
timeout = self.app.config["RESPONSE_TIMEOUT"]   # default 60
try:
    await asyncio.wait_for(self._send_response(send, response), timeout=timeout)
except asyncio.TimeoutError:
    pass   # ← 60초 경과 시 응답 전송 중단 → TCP close
```

장시간 SSE / streaming 응답을 상정하지 않은 기본 설정. `RESPONSE_TIMEOUT=60`은 비스트리밍 API의 폭주 방지가 목적이지만 SSE에는 치명적.

### 해결책

Quart `Response` 객체에 **응답별 timeout 오버라이드** 설정:

```python
resp = Response(
    sse_generator(),
    mimetype="text/event-stream",
    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
)
resp.timeout = None  # disable RESPONSE_TIMEOUT for SSE
return resp
```

`Response.timeout`의 기본값은 `Ellipsis`이며, `Ellipsis`인 경우에만 `app.config["RESPONSE_TIMEOUT"]`이 사용되는 사양(`asgi.py:112-115`). `None`을 명시하면 timeout 무제한.

**수정 commit**: `b35ed46cc`

적용 위치:
- `extensions/builtin_hailo_genai/hailo_chat_routes_send.py` — chat SSE
- `extensions/builtin_hailo_genai/hailo_llm_routes.py` — `/api/llm/generate` SSE
- `extensions/builtin_hailo_genai/openai_chat_stream.py` — OpenAI 호환 streaming (×2)

비 SSE 라우트는 건드리지 않음(60초 timeout은 보호 기구로서 유효).

### 교훈

- **Quart의 `RESPONSE_TIMEOUT`은 SSE에 치명적**. 새 SSE 엔드포인트를 추가할 때는 반드시 `resp.timeout = None`을 설정.
- "데이터가 흐르는데 끊어진다"면 idle timeout을 의심하지 말 것. 고정 최대 시간을 의심할 것.
- 절리는 **Wireshark에서 FIN의 발신지 IP**를 보는 것이 가장 빠름. tcpdump에서도 `tcp[tcpflags] & tcp-fin != 0` 필터로 가능.

---

## 2. cold_load 중의 SSE keepalive (60초 문제와는 별도의 예방책)

### 증상 예방

`RESPONSE_TIMEOUT`을 해제해도, **중간 네트워크(consumer router / 방화벽 / 브라우저 stream API)**가 장시간 idle 연결을 끊을 가능성은 별도로 존재. cold_load 중의 약 71초간 아무것도 보내지 않으면 중간 기기에 "dead"로 판정될 수 있음.

### 대책

`HailoLLMSubprocessClient.stream()`을 `stream_with_keepalive()`로 래핑하여 **5초 간격으로 keepalive 데이터 이벤트** 전송:

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
                    yield ("ping", None)   # 5초 무음 시 keepalive
```

route 측에서 `("ping", None)`을 수신하면 `data: {"keepalive": true}\n\n`을 yield. 클라이언트(chat UI)는 `d.token` / `d.error` / `d.done` 중 어느 것에도 해당하지 않는 이벤트를 조용히 무시.

### SSE comment(`: keepalive`) 대신 `data:` event를 사용하는 이유

처음에 `: keepalive\n\n`(SSE comment)를 시도했지만 검증 환경에서 효과 없음. `data: {"keepalive":true}`(실제 데이터 이벤트)로 변경. SSE 사양상으로는 comment도 유효하지만, 일부 중간 기기·브라우저 구현은 comment 행을 "무시 가능한 메타데이터"로 취급하여 실제 데이터가 없는 idle로 판정하는 것으로 보임. 실제 이벤트가 더 범용적.

**수정 commits**: `d450297c2`, `213b9c962`, `dff60989c`

---

## 3. Worker Subprocess가 시작 직후 종료되는 루프

### 증상

`logs/inference_worker.log`:

```
22:46:29 Inference worker started (pid=1612)
22:46:31 Inference worker shutting down   ← 2초 후 정상 종료
22:46:32 Inference worker started (pid=1615)
22:46:34 Inference worker shutting down
...
22:46:41 Worker crashed and max restarts exhausted
```

worker가 시작하고 2초 만에 "정상 shutdown", 부모가 `is_alive=False` 감지 → 재시작을 3회 반복 후 포기, auto-restart pool 소진.

### 근본 원인

`worker_process.worker_main`의 메인 루프:

```python
while True:
    task = queue.get_task(timeout=2.0)
    if task is None or isinstance(task, ShutdownSentinel):   # ← bug
        logger.info("Inference worker shutting down")
        break
```

`get_task(timeout=2.0)`은 task가 없을 경우 None을 반환. 이를 `ShutdownSentinel`과 동일하게 취급하여 break. worker는 시작 직후 2초간 task 대기 → 취득 실패로 None → "shutdown 명령"으로 오인 → break → 부모가 `is_alive=False` 감지 → 재시작 루프.

### 해결책

```python
if task is None:
    continue                            # timeout은 polling 계속
if isinstance(task, ShutdownSentinel):
    break                                # 명시적 shutdown만 break
```

**수정 commit**: `af19f16de`

### 교훈

- `multiprocessing.Queue.get(timeout=...)`의 `None`은 "timeout"을 의미. "queue 종료"는 `ShutdownSentinel` 등의 명시적 sentinel로 표현. 양자를 혼동하지 말 것.

---

## 4. Worker가 daemon=True로 인해 hailo_platform이 내부 Subprocess를 실행할 수 없음

### 증상

실기 초회 chat 시 `Worker crashed` 로그. stderr 캡처 없이 원인 불명.

### 근본 원인 가설

`bridge.start()`:

```python
self._process = ctx.Process(
    target=worker_main,
    args=(...),
    daemon=True,                    # ← 문제
    ...
)
```

`multiprocessing.Process(daemon=True)`는 부모 프로세스 종료 시 자식을 자동 kill하지만, **daemonic process는 자신의 자식 프로세스를 spawn할 수 없음**(`AssertionError: daemonic processes are not allowed to have children`). HailoRT 내부에서 어떤 helper process / thread를 실행할 경우 죽음.

### 해결책

```python
daemon=False
```

대신 `@app.after_serving`에서 명시적으로 `inference_bridge.stop(timeout=5.0)`을 호출하여 클린 셧다운.

**수정 commit**: `cf49a42a2` (worker logging diagnostics 추가와 함께)

### 교훈

- HailoRT 같은 C 확장 기반 라이브러리를 사용하는 subprocess는 `daemon=False`로 설정.
- subprocess 정리는 `@app.after_serving`에서 명시적으로.

---

## 5. Spawn된 Worker Subprocess의 stderr / logger 출력이 캡처되지 않음

### 증상

worker subprocess 내의 예외 traceback이 **어디에도 남지 않음**. stdout/stderr가 부모 프로세스로 라우팅되지 않고, logger 설정도 상속되지 않음(spawn의 특성).

### 해결책

`worker_main` 서두에 **전용 logging handler** 부착:

```python
def _configure_worker_logging() -> None:
    log_path = project_root / "logs" / "inference_worker.log"
    handler = RotatingFileHandler(log_path, maxBytes=2*1024*1024, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] (%(name)s pid=%(process)d) %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
```

추가로 `worker_main` 전체를 `try/except BaseException: logger.critical(traceback.format_exc())`로 래핑하여 import 시 오류도 포착.

**수정 commit**: `cf49a42a2`

### 교훈

- `multiprocessing.get_context("spawn").Process`는 부모의 logging 설정을 상속하지 않음. **spawn된 측에서 명시적으로 setup**.
- daemon thread의 예외도 기본적으로 무시됨(`threading.Thread` 기본 동작). control daemon에도 try/except + log를 추가.

---

## 6. bridge.iter_stream의 inter-token timeout이 cold_load에 너무 짧음

### 증상

초회 chat에서 `[WARN] Stream timeout for task ...`가 로그에 출력되고, 토큰이 도착하기 전에 SSE 종료.

### 근본 원인

`bridge.iter_stream`의 queue.get timeout이 **10초 고정**이었기 때문에, cold_load(71초) 중에 first token이 오지 않아 timeout.

### 해결책

spec §3.4 방침에 맞춰:

- `first_token_timeout = 120.0` (cold_load 71s + 여유 50s)
- `inter_token_timeout = 30.0` (토큰 간격 상한)
- 첫 번째 token 수신 후 짧은 timeout으로 전환

**수정 commit**: `35d556150`

---

## 7. handler_hailo_llm이 prompt normalisation을 skip하여 HailoRT InvalidOperation

### 증상

두 번째 이후 chat 전송 시 `HailoRTInvalidOperationException`. HailoRT 로그:

```
[HailoRT] [error] CHECK failed - System role messages can only be provided on the first prompt
```

### 근본 원인

subprocess handler가 messages를 그대로 `llm.generate(prompt=messages)`에 전달하여, in-process `HailoLLM._prepare_prompt`의 전처리를 skip:

- 구조화된 콘텐츠 `[{"type":"text","text":"..."}]` → plain string 평탄화 누락
- context 계속 시(두 번째 턴 이후) system role 제거 누락

HailoRT chat template은 이 두 가지를 전제로 함.

### 해결책

`_normalise_prompt`를 공유 import + context 계속 시 system role 제거:

```python
normalised = _normalise_prompt(messages)
if llm_instance.get_context_usage_size() > 0:
    normalised = [m for m in normalised if m.get("role") != "system"]
```

**수정 commit**: `cdd9e26fe`

### 교훈

- in-process와 subprocess 양쪽 경로를 구현할 경우, in-process 측에서 수행하는 pre/post-processing을 **양쪽에서 동일하게 적용**하는 것을 설계 시 확인. spec §3.5의 device_manager 부모-자식 상태 분리 대책과 마찬가지로, 공통 라이브러리화가 바람직.

---

## 8. cold_load 중 cancel의 race 지연

### 증상 (잠재)

cold_load(71초) 중에는 HailoRT C 확장이 GIL을 보유하기 때문에 worker의 control daemon thread가 동작할 수 없어, 사용자 연결 끊김 시의 `ControlMessage(op="cancel")`이 처리되지 않음. cold_load 완료 직후 `generate()`를 호출하면 버려진 task를 위해 토큰 생성이 시작됨.

### 해결책

`acquire_genai()` 완료 후 50ms 대기 → control daemon이 pending cancel을 처리할 여지를 줌 → `cancel_flags[task_id]` 확인 → True이면 generate() skip:

```python
import time as _time
_time.sleep(0.05)
if cancel_flags.get(task_id, False):
    _emit_terminal(queue, task_id, seq, error="cancelled")
    return InferenceResult(task_id=task_id, status=TaskStatus.CANCELLED, error="cancelled")
```

**수정 commit**: `5fbb02d95`

---

## 9. inference_worker.start()를 호출하는 시작 경로가 production에 존재하지 않음

### 증상

config에서 `hailo_genai.llm_subprocess: true`를 설정해도, chat 전송 시 `RuntimeError("Failed to submit LLM task to worker")`.

### 근본 원인

`@app.before_serving`에서 `bind_event_loop(loop)`만 실행되고 있었으며, 핵심 `inference_bridge.start(db_path, config)` 호출이 production에 **존재하지 않았음**. worker process가 영원히 spawn되지 않는 상태.

### 해결책

`@app.before_serving`에서 `start()` → `bind_event_loop()` 순서로 실행, `@app.after_serving`에서 `stop()`:

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

**수정 commit**: `9053f2f72`

---

## 완성된 수정 목록 (시간순)

| Commit | 내용 |
|--------|------|
| `9053f2f72` | app.before_serving에서 inference_bridge.start() 호출 |
| `cf49a42a2` | worker logging diagnostics + daemon=False + auto-restart의 db_path 보존 |
| `af19f16de` | queue timeout을 continue로 수정 |
| `35d556150` | iter_stream first_token_timeout 120s, inter_token 30s |
| `d450297c2` | SSE keepalive comment 도입 |
| `cdd9e26fe` | handler에 prompt normalisation 추가 |
| `213b9c962` | keepalive 간격 15s → 5s + 진단 로그 |
| `dff60989c` | keepalive를 `: comment` → `data:` event화 |
| `b35ed46cc` | **Quart RESPONSE_TIMEOUT 60s를 SSE에서 해제 (근본 원인)** |
| `5fbb02d95` | cold_load 후 조기 cancel check |

---

## 관련 문서

- spec 본체: `docs/superpowers/specs/2026-05-17-hailo-llm-subprocess-gil-unblock-design.md`
- 관련 (REJECTED): `docs/superpowers/specs/2026-05-17-hailo-subprocess-isolation-design.md`
- CMA leak: `docs/ja/hailo/HAILO_CMA_LEAK_HAILORT_5_3_0.md`
- VDevice 공유: `docs/ja/hailo/VDEVICE_SHARING_PATTERN.md`
