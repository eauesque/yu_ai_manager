# Hailo LLM Subprocess GIL Unblock — 実装デブログ

- **対象**: HailoRT Python binding の cold_load (~71秒) 中に Quart event loop が GIL に阻まれて固まる問題の解消
- **手法**: LLM chat 推論を `core/inference_worker/` の subprocess に隔離
- **spec**: `docs/superpowers/specs/2026-05-17-hailo-llm-subprocess-gil-unblock-design.md`
- **完了 phase**: 0a / 0b / 1 (実機検証済み)

本ドキュメントは実装途中で遭遇した非自明な障害と解決策をまとめる。特に SSE 60 秒 drop は調査に時間を要したので、後続が同じ罠を踏まないよう記録する。

---

## 1. SSE が 60 秒で必ず切れる ("Stream interrupted: network error")

### 症状

`/ext/hailo-genai/api/chat/send` の SSE レスポンスが、cold_load 中・トークン生成中に関係なく **正確に 60 秒で TCP 切断**。

- ブラウザ: `Stream interrupted: network error`
- curl: `curl: (18) transfer closed with outstanding read data remaining`
- アクセスログ: `POST ... 1.1 - - 60236944` (status `-`, duration 60.2 秒)

データが連続して流れていても (e.g., 30 tok/s) 切れるため idle timeout ではない。

### 切り分け

1. **ローカル loopback でも切れる** (`http://127.0.0.1:5000/...` を Pi 上で curl) → 中間ネットワークではなく Pi 側
2. **Wireshark で FIN の発信元確認** — 192.168.50.4 (Pi) → 192.168.50.247 (client) の FIN が `connection_start + 60.006s` で送信。**Pi 側起点で確定**
3. Hypercorn の documented timeouts (`keep_alive_timeout=5s`, `read_timeout=None`, `shutdown_timeout=60s` 等) のいずれも active response には適用されない

### 真因

**Quart の `RESPONSE_TIMEOUT` 設定 (デフォルト 60 秒)**

`quart/asgi.py:117`:

```python
timeout = self.app.config["RESPONSE_TIMEOUT"]   # default 60
try:
    await asyncio.wait_for(self._send_response(send, response), timeout=timeout)
except asyncio.TimeoutError:
    pass   # ← 60s 経過で response 送信を中止 → TCP close
```

長時間 SSE / streaming レスポンスを想定していない default 設定。`RESPONSE_TIMEOUT=60` は非ストリーミング API の暴走防止が目的だが、SSE には致命的。

### 解決策

Quart `Response` オブジェクトに **per-response の timeout 上書き** を設定:

```python
resp = Response(
    sse_generator(),
    mimetype="text/event-stream",
    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
)
resp.timeout = None  # disable RESPONSE_TIMEOUT for SSE
return resp
```

`Response.timeout` の default は `Ellipsis` で、`Ellipsis` の場合のみ `app.config["RESPONSE_TIMEOUT"]` が使われる仕様 (`asgi.py:112-115`)。`None` を明示すれば timeout 無制限。

**修正 commit**: `b35ed46cc`

適用箇所:
- `extensions/builtin_hailo_genai/hailo_chat_routes_send.py` — chat SSE
- `extensions/builtin_hailo_genai/hailo_llm_routes.py` — `/api/llm/generate` SSE
- `extensions/builtin_hailo_genai/openai_chat_stream.py` — OpenAI 互換 streaming (×2)

非 SSE ルートには触れない (60 秒 timeout は保護機構として有用)。

### 教訓

- **Quart の `RESPONSE_TIMEOUT` は SSE には致命的**。新規 SSE エンドポイントを追加するときは必ず `resp.timeout = None` を設定する。
- 「データが流れているのに切れる」場合は idle timeout を疑わない。固定 max-duration を疑う。
- 切り分けは **Wireshark で FIN の発信元 IP** を見るのが最速。tcpdump でも `tcp[tcpflags] & tcp-fin != 0` フィルタで OK。

---

## 2. cold_load 中の SSE keepalive (60s 問題と別途の予防策)

### 症状予防

`RESPONSE_TIMEOUT` を解除しても、**中間ネットワーク (consumer router / firewall / browser stream API)** が長時間 idle 接続を切る可能性は別途存在する。cold_load 中の ~71 秒は何も送らないと中間機器に "dead" 判定される。

### 対策

`HailoLLMSubprocessClient.stream()` を `stream_with_keepalive()` でラップし、**5 秒間隔で keepalive データイベント** を送信:

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
                    yield ("ping", None)   # 5s 無音時に keepalive
```

route 側で `("ping", None)` を受け取ったら `data: {"keepalive": true}\n\n` を yield。クライアント (chat UI) は `d.token` / `d.error` / `d.done` のどれにも該当しない event を silent ignore する。

### SSE comment (`: keepalive`) ではなく `data:` event を使う理由

最初 `: keepalive\n\n` (SSE コメント) を試したが、検証中の環境では効果なし。`data: {"keepalive":true}` (本物のデータイベント) に変えた。SSE 仕様上はコメントも有効だが、一部の中間機器・ブラウザ実装はコメント行を「無視可能なメタデータ」として扱い、本物のデータが来ない idle と判定する模様。本物の event のほうが汎用的。

**修正 commits**: `d450297c2`, `213b9c962`, `dff60989c`

---

## 3. Worker subprocess が起動直後に終了するループ

### 症状

`logs/inference_worker.log`:

```
22:46:29 Inference worker started (pid=1612)
22:46:31 Inference worker shutting down   ← 2 秒後に正常終了
22:46:32 Inference worker started (pid=1615)
22:46:34 Inference worker shutting down
...
22:46:41 Worker crashed and max restarts exhausted
```

worker が起動して 2 秒で「正常 shutdown」、親が `is_alive=False` 検知 → restart を 3 回繰り返して諦め、auto-restart pool 枯渇。

### 真因

`worker_process.worker_main` のメインループ:

```python
while True:
    task = queue.get_task(timeout=2.0)
    if task is None or isinstance(task, ShutdownSentinel):   # ← bug
        logger.info("Inference worker shutting down")
        break
```

`get_task(timeout=2.0)` は task がない場合 None を返す。これを `ShutdownSentinel` と同列に扱って break していた。worker は起動直後 2 秒間 task 待ち → 取得失敗で None → 「shutdown 命令」と誤認 → break → 親が is_alive=False 検知 → restart loop。

### 解決策

```python
if task is None:
    continue                            # timeout は polling 継続
if isinstance(task, ShutdownSentinel):
    break                                # 明示的 shutdown のみ break
```

**修正 commit**: `af19f16de`

### 教訓

- `multiprocessing.Queue.get(timeout=...)` の `None` は「timeout」を意味する。「end of queue」は `ShutdownSentinel` 等の明示的 sentinel で表現する。両者を混同しないこと。

---

## 4. Worker が daemon=True で hailo_platform が内部 subprocess 起こせない

### 症状

実機で初回 chat 時に `Worker crashed` ログ。stderr 捕捉なしのため原因不明。

### 真因仮説

`bridge.start()`:

```python
self._process = ctx.Process(
    target=worker_main,
    args=(...),
    daemon=True,                    # ← problem
    ...
)
```

`multiprocessing.Process(daemon=True)` は親プロセス終了時に子を自動 kill するが、**daemonic process は自身の子プロセスを spawn できない** (`AssertionError: daemonic processes are not allowed to have children`)。HailoRT 内部で何らかの helper process / thread を起こす場合に死ぬ。

### 解決策

```python
daemon=False
```

代わりに `@app.after_serving` で明示的に `inference_bridge.stop(timeout=5.0)` を呼んでクリーンシャットダウン。

**修正 commit**: `cf49a42a2` (worker logging diagnostics 追加と合わせて)

### 教訓

- HailoRT のような C 拡張ベースのライブラリを使う subprocess は `daemon=False` にする。
- subprocess のクリーンアップは `@app.after_serving` で明示的に。

---

## 5. spawn された worker subprocess の stderr / logger 出力が捕捉されない

### 症状

worker subprocess 内の例外 traceback が **どこにも残らない**。stdout/stderr が親プロセスにルーティングされず、logger 設定も継承されない (spawn の特性)。

### 解決策

`worker_main` の冒頭で **dedicated logging handler** を attach:

```python
def _configure_worker_logging() -> None:
    log_path = project_root / "logs" / "inference_worker.log"
    handler = RotatingFileHandler(log_path, maxBytes=2*1024*1024, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] (%(name)s pid=%(process)d) %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
```

加えて `worker_main` 全体を `try/except BaseException: logger.critical(traceback.format_exc())` でラップし、import-time エラーも補足。

**修正 commit**: `cf49a42a2`

### 教訓

- `multiprocessing.get_context("spawn").Process` は親の logging 設定を継承しない。**spawn された側で明示的に setup する**。
- daemon thread の例外も基本的に握り潰される (`threading.Thread` default behavior)。control daemon にも try/except + log を入れる。

---

## 6. bridge.iter_stream の inter-token timeout が cold_load に短すぎる

### 症状

初回 chat で `[WARN] Stream timeout for task ...` がログに出て、トークンが届く前に SSE 終了。

### 真因

`bridge.iter_stream` の queue.get timeout が **10 秒固定**だったため、cold_load (71 秒) 中に first token が来ず timeout。

### 解決策

spec §3.4 の方針に合わせて:

- `first_token_timeout = 120.0` (cold_load 71s + 余裕 50s)
- `inter_token_timeout = 30.0` (token 間隔上限)
- 最初の token 受信後に short timeout に切替

**修正 commit**: `35d556150`

---

## 7. handler_hailo_llm が prompt normalisation を skip して HailoRT InvalidOperation

### 症状

2 回目以降の chat 送信で `HailoRTInvalidOperationException`。HailoRT ログ:

```
[HailoRT] [error] CHECK failed - System role messages can only be provided on the first prompt
```

### 真因

subprocess handler が messages を生のまま `llm.generate(prompt=messages)` に渡しており、in-process `HailoLLM._prepare_prompt` の前処理を skip していた:

- structured content `[{"type":"text","text":"..."}]` → plain string への平坦化が抜け
- context 継続時 (2 ターン目以降) の system role 除去が抜け

HailoRT chat template はこの 2 つを前提にしている。

### 解決策

`_normalise_prompt` を共有 import + context 継続時の system role 除去:

```python
normalised = _normalise_prompt(messages)
if llm_instance.get_context_usage_size() > 0:
    normalised = [m for m in normalised if m.get("role") != "system"]
```

**修正 commit**: `cdd9e26fe`

### 教訓

- in-process と subprocess の両経路を実装する場合、in-process 側で実施している pre/post-processing を **両方で同じく適用**することを設計時に確認。 spec §3.5 の device_manager の親子 state 分裂対策と同じく、共通ライブラリ化が望ましい。

---

## 8. cold_load 中の cancel が遅延する race

### 症状 (潜在)

cold_load 中 (71s) は HailoRT C 拡張が GIL を保持するため worker の control daemon thread が動けず、ユーザー切断時の `ControlMessage(op="cancel")` が処理されない。cold_load 完了直後に直接 `generate()` を呼ぶと、捨てられたタスクのためにトークン生成を開始してしまう。

### 解決策

`acquire_genai()` 完了後に 50ms 待機 → control daemon が pending cancel を処理する余地を与える → `cancel_flags[task_id]` チェック → True なら generate() を skip:

```python
import time as _time
_time.sleep(0.05)
if cancel_flags.get(task_id, False):
    _emit_terminal(queue, task_id, seq, error="cancelled")
    return InferenceResult(task_id=task_id, status=TaskStatus.CANCELLED, error="cancelled")
```

**修正 commit**: `5fbb02d95`

---

## 9. inference_worker.start() を呼ぶ起動経路が production に存在しなかった

### 症状

config で `hailo_genai.llm_subprocess: true` を設定しても、chat 送信時に `RuntimeError("Failed to submit LLM task to worker")`。

### 真因

`bind_event_loop(loop)` だけが `@app.before_serving` で実行されており、肝心の `inference_bridge.start(db_path, config)` を呼ぶコードが production に **存在しなかった**。worker process が永遠に spawn されない状態。

### 解決策

`@app.before_serving` で `start()` → `bind_event_loop()` の順に実行、`@app.after_serving` で `stop()`:

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

**修正 commit**: `9053f2f72`

---

## 完成した修正一覧 (時系列)

| Commit | 内容 |
|--------|------|
| `9053f2f72` | inference_bridge.start() を app.before_serving で呼ぶ |
| `cf49a42a2` | worker logging diagnostics + daemon=False + auto-restart の db_path 保持 |
| `af19f16de` | queue timeout を continue に修正 |
| `35d556150` | iter_stream first_token_timeout 120s, inter_token 30s |
| `d450297c2` | SSE keepalive comment 導入 |
| `cdd9e26fe` | handler に prompt normalisation 追加 |
| `213b9c962` | keepalive 間隔 15s → 5s + 診断ログ |
| `dff60989c` | keepalive を `: comment` → `data:` event 化 |
| `b35ed46cc` | **Quart RESPONSE_TIMEOUT 60s を SSE で解除 (真因)** |
| `5fbb02d95` | cold_load 後の早期 cancel check |

---

## 関連ドキュメント

- spec 本体: `docs/superpowers/specs/2026-05-17-hailo-llm-subprocess-gil-unblock-design.md`
- 関連 (REJECTED): `docs/superpowers/specs/2026-05-17-hailo-subprocess-isolation-design.md`
- CMA leak: `docs/ja/hailo/HAILO_CMA_LEAK_HAILORT_5_3_0.md`
- VDevice 共有: `docs/ja/hailo/VDEVICE_SHARING_PATTERN.md`
