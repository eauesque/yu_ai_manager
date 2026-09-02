# Hailo LLM Subprocess GIL Unblock — Журнал Разработки Реализации

- **Цель**: Устранение проблемы, при которой event loop Quart зависает из-за GIL во время cold_load (~71 секунды) Python-привязки HailoRT
- **Метод**: Изоляция инференса чата LLM в subprocess под `core/inference_worker/`
- **spec**: `docs/superpowers/specs/2026-05-17-hailo-llm-subprocess-gil-unblock-design.md`
- **Завершённые фазы**: 0a / 0b / 1 (проверено на реальном оборудовании)

Данный документ обобщает неочевидные сбои и решения, встреченные в процессе реализации. Особенно прерывание SSE через 60 секунд потребовало значительного времени на расследование, поэтому оно задокументировано здесь, чтобы другие не попали в ту же ловушку.

---

## 1. SSE всегда обрывается через 60 секунд ("Stream interrupted: network error")

### Симптом

Ответ SSE от `/ext/hailo-genai/api/chat/send` приводит к **TCP-разрыву ровно через 60 секунд**, независимо от того, идёт ли cold_load или генерируются токены.

- Браузер: `Stream interrupted: network error`
- curl: `curl: (18) transfer closed with outstanding read data remaining`
- Лог доступа: `POST ... 1.1 - - 60236944` (status `-`, длительность 60,2 секунды)

Даже когда данные текут непрерывно (например, 30 tok/s), соединение обрывается — следовательно, это не idle timeout.

### Локализация

1. **Обрывается также на локальном loopback** (`http://127.0.0.1:5000/...` через curl на Pi) → проблема не в промежуточной сети, а на стороне Pi
2. **Происхождение FIN подтверждено через Wireshark** — FIN отправлен с 192.168.50.4 (Pi) → 192.168.50.247 (клиент) в момент `connection_start + 60.006s`. **Подтверждено происхождение со стороны Pi**
3. Ни один из задокументированных timeout-ов Hypercorn (`keep_alive_timeout=5s`, `read_timeout=None`, `shutdown_timeout=60s` и др.) не применяется к активным ответам

### Корневая Причина

**Настройка `RESPONSE_TIMEOUT` Quart (по умолчанию 60 секунд)**

`quart/asgi.py:117`:

```python
timeout = self.app.config["RESPONSE_TIMEOUT"]   # default 60
try:
    await asyncio.wait_for(self._send_response(send, response), timeout=timeout)
except asyncio.TimeoutError:
    pass   # ← через 60с отправка ответа прерывается → TCP close
```

Настройка по умолчанию не рассчитана на длительные SSE / streaming ответы. `RESPONSE_TIMEOUT=60` предназначен для предотвращения выхода из-под контроля нестриминговых API, но губителен для SSE.

### Решение

Установить **переопределение timeout для конкретного ответа** на объекте `Response` Quart:

```python
resp = Response(
    sse_generator(),
    mimetype="text/event-stream",
    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
)
resp.timeout = None  # disable RESPONSE_TIMEOUT for SSE
return resp
```

Значение по умолчанию `Response.timeout` — `Ellipsis`, и `app.config["RESPONSE_TIMEOUT"]` используется только когда значение равно `Ellipsis` (`asgi.py:112-115`). Явная установка `None` полностью отключает timeout.

**Коммит исправления**: `b35ed46cc`

Применённые места:
- `extensions/builtin_hailo_genai/hailo_chat_routes_send.py` — chat SSE
- `extensions/builtin_hailo_genai/hailo_llm_routes.py` — `/api/llm/generate` SSE
- `extensions/builtin_hailo_genai/openai_chat_stream.py` — совместимый с OpenAI streaming (×2)

Не-SSE маршруты не затрагиваются (timeout в 60 секунд там полезен как механизм защиты).

### Уроки

- **`RESPONSE_TIMEOUT` Quart губителен для SSE**. При добавлении нового SSE endpoint всегда устанавливать `resp.timeout = None`.
- Когда «данные текут, но соединение обрывается», не подозревать idle timeout. Подозревать фиксированную максимальную продолжительность.
- Быстрейший способ локализации — **посмотреть IP источника FIN в Wireshark**. В tcpdump также работает фильтр `tcp[tcpflags] & tcp-fin != 0`.

---

## 2. Keepalive SSE во время cold_load (Превентивная мера, отдельная от проблемы 60 секунд)

### Предотвращение Симптомов

Даже после отключения `RESPONSE_TIMEOUT`, по-прежнему существует отдельная возможность того, что **промежуточные сети (потребительские роутеры / файрволы / stream API браузера)** будут обрывать длительные idle-соединения. ~71 секунда тишины во время cold_load может быть расценена промежуточными устройствами как «мёртвое» соединение.

### Контрмера

Обернуть `HailoLLMSubprocessClient.stream()` в `stream_with_keepalive()` для отправки **keepalive-событий данных каждые 5 секунд**:

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
                    yield ("ping", None)   # keepalive при 5с тишины
```

Когда маршрут получает `("ping", None)`, он выдаёт `data: {"keepalive": true}\n\n`. Клиент (chat UI) молча игнорирует события, не соответствующие `d.token` / `d.error` / `d.done`.

### Почему используются события `data:`, а не SSE-комментарии (`: keepalive`)

Изначально был опробован `: keepalive\n\n` (SSE-комментарий), но в тестовой среде он оказался неэффективным. Переход на `data: {"keepalive":true}` (настоящее событие данных) решил проблему. Хотя SSE-комментарии допустимы по спецификации, некоторые промежуточные устройства и реализации браузеров трактуют строки комментариев как «игнорируемые метаданные» и всё равно считают соединение idle, если не приходят реальные данные. Реальные события более универсально совместимы.

**Коммиты исправлений**: `d450297c2`, `213b9c962`, `dff60989c`

---

## 3. Subprocess воркера завершается сразу после запуска в цикле

### Симптом

`logs/inference_worker.log`:

```
22:46:29 Inference worker started (pid=1612)
22:46:31 Inference worker shutting down   ← нормальное завершение через 2 секунды
22:46:32 Inference worker started (pid=1615)
22:46:34 Inference worker shutting down
...
22:46:41 Worker crashed and max restarts exhausted
```

Воркер запускается, «чисто завершается» через 2 секунды, родительский процесс обнаруживает `is_alive=False` → перезапускает 3 раза и сдаётся; пул автоперезапуска исчерпан.

### Корневая Причина

Основной цикл `worker_process.worker_main`:

```python
while True:
    task = queue.get_task(timeout=2.0)
    if task is None or isinstance(task, ShutdownSentinel):   # ← bug
        logger.info("Inference worker shutting down")
        break
```

`get_task(timeout=2.0)` возвращает `None`, когда нет доступных задач. Это обрабатывалось так же, как `ShutdownSentinel`, вызывая break. Воркер ждёт 2 секунды задачу → получение не удаётся, возвращает `None` → ошибочно интерпретируется как «команда shutdown» → break → родитель обнаруживает `is_alive=False` → цикл перезапуска.

### Решение

```python
if task is None:
    continue                            # timeout → продолжить поллинг
if isinstance(task, ShutdownSentinel):
    break                                # break только при явном shutdown
```

**Коммит исправления**: `af19f16de`

### Уроки

- `None` от `multiprocessing.Queue.get(timeout=...)` означает «timeout», а не «конец очереди». «Конец очереди» должен выражаться явным sentinel-ом, например `ShutdownSentinel`. Не путать одно с другим.

---

## 4. Воркер не может запустить внутренний Subprocess hailo_platform из-за daemon=True

### Симптом

Лог `Worker crashed` при первом чате на реальном оборудовании. Причина неизвестна из-за отсутствия захвата stderr.

### Гипотеза Корневой Причины

`bridge.start()`:

```python
self._process = ctx.Process(
    target=worker_main,
    args=(...),
    daemon=True,                    # ← проблема
    ...
)
```

`multiprocessing.Process(daemon=True)` автоматически убивает дочерние процессы при завершении родителя, но **демонизированные процессы не могут порождать собственные дочерние процессы** (`AssertionError: daemonic processes are not allowed to have children`). Завершается с ошибкой, если HailoRT внутренне запускает какой-либо вспомогательный процесс или поток.

### Решение

```python
daemon=False
```

Вместо этого явно вызвать `inference_bridge.stop(timeout=5.0)` в `@app.after_serving` для чистого завершения.

**Коммит исправления**: `cf49a42a2` (совместно с добавлением диагностики логирования воркера)

### Уроки

- Subprocess-ы, использующие библиотеки на основе C-расширений, такие как HailoRT, должны использовать `daemon=False`.
- Очистка subprocess-ов должна выполняться явно в `@app.after_serving`.

---

## 5. Вывод stderr / logger порождённого subprocess воркера не захватывается

### Симптом

Трассировки исключений внутри subprocess воркера **нигде не сохраняются**. stdout/stderr не направляется в родительский процесс, а конфигурация логгера не наследуется (особенность spawn).

### Решение

Прикрепить **специальный обработчик логирования** в начале `worker_main`:

```python
def _configure_worker_logging() -> None:
    log_path = project_root / "logs" / "inference_worker.log"
    handler = RotatingFileHandler(log_path, maxBytes=2*1024*1024, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] (%(name)s pid=%(process)d) %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
```

Дополнительно обернуть весь `worker_main` в `try/except BaseException: logger.critical(traceback.format_exc())` для захвата ошибок времени импорта.

**Коммит исправления**: `cf49a42a2`

### Уроки

- `multiprocessing.get_context("spawn").Process` не наследует конфигурацию логирования родителя. **Настраивать явно на порождённой стороне**.
- Исключения в daemon-потоках также по умолчанию молча поглощаются (поведение по умолчанию `threading.Thread`). Добавлять try/except + log также в control daemon-ы.

---

## 6. Межтокенный timeout bridge.iter_stream слишком короткий для cold_load

### Симптом

При первом чате в логе появляется `[WARN] Stream timeout for task ...`, и SSE завершается до прихода токенов.

### Корневая Причина

Timeout `queue.get` в `bridge.iter_stream` был **фиксирован на 10 секунд**, поэтому первый токен не приходит во время cold_load (71 секунда), вызывая timeout.

### Решение

Согласно политике spec §3.4:

- `first_token_timeout = 120.0` (cold_load 71с + 50с запаса)
- `inter_token_timeout = 30.0` (максимальный интервал между токенами)
- Переключиться на короткий timeout после получения первого токена

**Коммит исправления**: `35d556150`

---

## 7. handler_hailo_llm пропускает нормализацию Prompt, вызывая HailoRT InvalidOperation

### Симптом

`HailoRTInvalidOperationException` при втором и последующих отправках чата. Лог HailoRT:

```
[HailoRT] [error] CHECK failed - System role messages can only be provided on the first prompt
```

### Корневая Причина

Обработчик subprocess передавал сообщения в сыром виде напрямую в `llm.generate(prompt=messages)`, пропуская предобработку `HailoLLM._prepare_prompt` в in-process:

- Отсутствовало уплощение структурированного контента `[{"type":"text","text":"..."}]` → простая строка
- Отсутствовало удаление роли system при продолжении контекста (начиная со 2-го хода)

Шаблон чата HailoRT предполагает эти два преобразования.

### Решение

Совместно использовать `_normalise_prompt` через общий import + удалять роль system при продолжении контекста:

```python
normalised = _normalise_prompt(messages)
if llm_instance.get_context_usage_size() > 0:
    normalised = [m for m in normalised if m.get("role") != "system"]
```

**Коммит исправления**: `cdd9e26fe`

### Уроки

- При реализации как in-process, так и subprocess путей подтверждать на этапе проектирования, что пред/пост-обработка, выполняемая на стороне in-process, **применяется одинаково на обоих путях**. Как и в случае с контрмерой разделения состояния родитель-потомок device_manager в spec §3.5, предпочтительно вынести это в общую библиотеку.

---

## 8. Отмена во время cold_load задерживается из-за состояния гонки

### Симптом (Скрытый)

Во время cold_load (71с) C-расширение HailoRT удерживает GIL, не позволяя потоку control daemon воркера работать. Как следствие, `ControlMessage(op="cancel")` при отключении пользователя не обрабатывается. Если `generate()` вызывается сразу после завершения cold_load, генерация токенов начинается для заброшенной задачи.

### Решение

После завершения `acquire_genai()` подождать 50мс → дать control daemon время обработать ожидающие отмены → проверить `cancel_flags[task_id]` → если True, пропустить generate():

```python
import time as _time
_time.sleep(0.05)
if cancel_flags.get(task_id, False):
    _emit_terminal(queue, task_id, seq, error="cancelled")
    return InferenceResult(task_id=task_id, status=TaskStatus.CANCELLED, error="cancelled")
```

**Коммит исправления**: `5fbb02d95`

---

## 9. В продакшне не существует пути кода, вызывающего inference_worker.start()

### Симптом

Даже с `hailo_genai.llm_subprocess: true` в конфигурации, отправка сообщения чата приводит к `RuntimeError("Failed to submit LLM task to worker")`.

### Корневая Причина

В `@app.before_serving` выполнялся только `bind_event_loop(loop)`; критический вызов `inference_bridge.start(db_path, config)` **не существовал в продакшне**. Процесс воркера никогда не порождался.

### Решение

Выполнять `start()` → `bind_event_loop()` по порядку в `@app.before_serving`, и `stop()` в `@app.after_serving`:

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

**Коммит исправления**: `9053f2f72`

---

## Полный список исправлений (Хронологический)

| Коммит | Описание |
|--------|----------|
| `9053f2f72` | Вызов inference_bridge.start() в app.before_serving |
| `cf49a42a2` | Диагностика логирования воркера + daemon=False + сохранение db_path для автоперезапуска |
| `af19f16de` | Исправление timeout очереди на continue |
| `35d556150` | iter_stream first_token_timeout 120с, inter_token 30с |
| `d450297c2` | Введение SSE keepalive-комментария |
| `cdd9e26fe` | Добавление нормализации prompt в обработчик |
| `213b9c962` | Интервал keepalive 15с → 5с + диагностические логи |
| `dff60989c` | Преобразование keepalive из `: comment` → событие `data:` |
| `b35ed46cc` | **Отключение Quart RESPONSE_TIMEOUT 60с для SSE (исправление корневой причины)** |
| `5fbb02d95` | Досрочная проверка отмены после cold_load |

---

## Связанные Документы

- Основной spec: `docs/superpowers/specs/2026-05-17-hailo-llm-subprocess-gil-unblock-design.md`
- Связанный (REJECTED): `docs/superpowers/specs/2026-05-17-hailo-subprocess-isolation-design.md`
- CMA leak: `docs/ja/hailo/HAILO_CMA_LEAK_HAILORT_5_3_0.md`
- VDevice sharing: `docs/ja/hailo/VDEVICE_SHARING_PATTERN.md`
