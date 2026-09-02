# Hailo LLM Subprocess GIL Unblock — Diario di Sviluppo dell'Implementazione

- **Obiettivo**: Risoluzione del problema in cui l'event loop di Quart si blocca a causa del GIL durante il cold_load (~71 secondi) del binding Python di HailoRT
- **Metodo**: Isolamento dell'inferenza chat LLM in un subprocess sotto `core/inference_worker/`
- **spec**: `docs/superpowers/specs/2026-05-17-hailo-llm-subprocess-gil-unblock-design.md`
- **Fasi completate**: 0a / 0b / 1 (verificate su hardware reale)

Questo documento riassume i guasti non ovvi e le soluzioni incontrate durante l'implementazione. La caduta SSE a 60 secondi in particolare ha richiesto un tempo di indagine considerevole, motivo per cui viene documentata qui per evitare che altri cadano nella stessa trappola.

---

## 1. SSE si interrompe sempre a 60 secondi ("Stream interrupted: network error")

### Sintomo

La risposta SSE da `/ext/hailo-genai/api/chat/send` provoca una **disconnessione TCP esattamente a 60 secondi**, indipendentemente dal fatto che cold_load sia in corso o che vengano generati token.

- Browser: `Stream interrupted: network error`
- curl: `curl: (18) transfer closed with outstanding read data remaining`
- Log di accesso: `POST ... 1.1 - - 60236944` (status `-`, durata 60,2 secondi)

Anche quando i dati scorrono continuamente (es. 30 tok/s), la connessione viene interrotta — non si tratta quindi di un idle timeout.

### Isolamento

1. **Si interrompe anche su loopback locale** (`http://127.0.0.1:5000/...` con curl sul Pi) → non è un problema di rete intermedia, ma dal lato Pi
2. **Origine del FIN confermata tramite Wireshark** — FIN inviato da 192.168.50.4 (Pi) → 192.168.50.247 (client) a `connection_start + 60.006s`. **Origine lato Pi confermata**
3. Nessuno dei timeout documentati di Hypercorn (`keep_alive_timeout=5s`, `read_timeout=None`, `shutdown_timeout=60s`, ecc.) si applica alle risposte attive

### Causa Radice

**Impostazione `RESPONSE_TIMEOUT` di Quart (predefinita a 60 secondi)**

`quart/asgi.py:117`:

```python
timeout = self.app.config["RESPONSE_TIMEOUT"]   # default 60
try:
    await asyncio.wait_for(self._send_response(send, response), timeout=timeout)
except asyncio.TimeoutError:
    pass   # ← dopo 60s, l'invio della risposta viene interrotto → TCP close
```

L'impostazione predefinita non considera le risposte SSE / streaming di lunga durata. `RESPONSE_TIMEOUT=60` è pensato per prevenire API non-streaming fuori controllo, ma è fatale per SSE.

### Soluzione

Impostare una **sovrascrittura del timeout per risposta** sull'oggetto `Response` di Quart:

```python
resp = Response(
    sse_generator(),
    mimetype="text/event-stream",
    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
)
resp.timeout = None  # disable RESPONSE_TIMEOUT for SSE
return resp
```

Il valore predefinito di `Response.timeout` è `Ellipsis`, e `app.config["RESPONSE_TIMEOUT"]` viene usato solo quando il valore è `Ellipsis` (`asgi.py:112-115`). Impostare esplicitamente `None` disabilita il timeout completamente.

**Commit di correzione**: `b35ed46cc`

Posizioni applicate:
- `extensions/builtin_hailo_genai/hailo_chat_routes_send.py` — chat SSE
- `extensions/builtin_hailo_genai/hailo_llm_routes.py` — `/api/llm/generate` SSE
- `extensions/builtin_hailo_genai/openai_chat_stream.py` — streaming compatibile OpenAI (×2)

Le route non-SSE non vengono toccate (il timeout di 60 secondi è utile come meccanismo di protezione lì).

### Lezioni Apprese

- **Il `RESPONSE_TIMEOUT` di Quart è fatale per SSE**. Quando si aggiunge un nuovo endpoint SSE, impostare sempre `resp.timeout = None`.
- Quando "i dati scorrono ma la connessione si interrompe", non sospettare un idle timeout. Sospettare una durata massima fissa.
- Il modo più rapido per isolare è **guardare l'IP di origine del FIN in Wireshark**. Con tcpdump funziona anche il filtro `tcp[tcpflags] & tcp-fin != 0`.

---

## 2. Keepalive SSE durante cold_load (Misura preventiva indipendente dal problema dei 60 secondi)

### Prevenzione dei Sintomi

Anche dopo aver disabilitato `RESPONSE_TIMEOUT`, esiste comunque la possibilità separata che le **reti intermedie (router consumer / firewall / API stream del browser)** taglino le connessioni idle di lunga durata. I ~71 secondi di silenzio durante cold_load possono essere giudicati "morti" dai dispositivi intermedi.

### Contromisura

Avvolgere `HailoLLMSubprocessClient.stream()` con `stream_with_keepalive()` per inviare **eventi di dati keepalive ogni 5 secondi**:

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
                    yield ("ping", None)   # keepalive dopo 5s di silenzio
```

Quando la route riceve `("ping", None)`, emette `data: {"keepalive": true}\n\n`. Il client (chat UI) ignora silenziosamente gli eventi che non corrispondono a `d.token` / `d.error` / `d.done`.

### Perché usare eventi `data:` invece di commenti SSE (`: keepalive`)

Inizialmente è stato provato `: keepalive\n\n` (commento SSE), ma si è rivelato inefficace nell'ambiente di test. Il passaggio a `data: {"keepalive":true}` (vero evento di dati) ha risolto il problema. Sebbene i commenti SSE siano validi secondo la specifica, alcuni dispositivi intermedi e implementazioni del browser trattano le righe di commenti come "metadati ignorabili" e giudicano comunque la connessione come idle quando non arrivano dati reali. Gli eventi reali sono più universalmente compatibili.

**Commit di correzione**: `d450297c2`, `213b9c962`, `dff60989c`

---

## 3. Il Subprocess Worker termina immediatamente dopo l'avvio in un ciclo

### Sintomo

`logs/inference_worker.log`:

```
22:46:29 Inference worker started (pid=1612)
22:46:31 Inference worker shutting down   ← arresto normale dopo 2 secondi
22:46:32 Inference worker started (pid=1615)
22:46:34 Inference worker shutting down
...
22:46:41 Worker crashed and max restarts exhausted
```

Il worker si avvia, "si spegne pulitamente" dopo 2 secondi, il processo padre rileva `is_alive=False` → riavvia 3 volte e si arrende; il pool di auto-riavvio è esaurito.

### Causa Radice

Il ciclo principale di `worker_process.worker_main`:

```python
while True:
    task = queue.get_task(timeout=2.0)
    if task is None or isinstance(task, ShutdownSentinel):   # ← bug
        logger.info("Inference worker shutting down")
        break
```

`get_task(timeout=2.0)` restituisce `None` quando nessuna task è disponibile. Questo veniva trattato allo stesso modo di `ShutdownSentinel`, causando un break. Il worker attende 2 secondi per un task → il recupero fallisce, restituisce `None` → malinterpretato come "comando di shutdown" → break → il padre rileva `is_alive=False` → ciclo di riavvio.

### Soluzione

```python
if task is None:
    continue                            # timeout → continuare il polling
if isinstance(task, ShutdownSentinel):
    break                                # break solo su shutdown esplicito
```

**Commit di correzione**: `af19f16de`

### Lezioni Apprese

- `None` da `multiprocessing.Queue.get(timeout=...)` significa "timeout", non "fine della coda". "Fine della coda" deve essere espresso usando un sentinel esplicito come `ShutdownSentinel`. Non confondere i due.

---

## 4. Il Worker non può avviare il Subprocess interno di hailo_platform perché daemon=True

### Sintomo

Log `Worker crashed` al primo chat su hardware reale. Causa sconosciuta perché non viene catturato stderr.

### Ipotesi di Causa Radice

`bridge.start()`:

```python
self._process = ctx.Process(
    target=worker_main,
    args=(...),
    daemon=True,                    # ← problema
    ...
)
```

`multiprocessing.Process(daemon=True)` uccide automaticamente i figli quando il padre termina, ma **i processi demone non possono generare i propri processi figli** (`AssertionError: daemonic processes are not allowed to have children`). Fallisce se HailoRT avvia internamente qualsiasi processo o thread ausiliario.

### Soluzione

```python
daemon=False
```

Invece, chiamare esplicitamente `inference_bridge.stop(timeout=5.0)` in `@app.after_serving` per uno spegnimento pulito.

**Commit di correzione**: `cf49a42a2` (combinato con l'aggiunta di diagnostica di logging del worker)

### Lezioni Apprese

- I subprocess che usano librerie basate su estensioni C come HailoRT dovrebbero usare `daemon=False`.
- La pulizia dei subprocess dovrebbe essere eseguita esplicitamente in `@app.after_serving`.

---

## 5. L'output stderr / logger del Subprocess Worker generato non viene catturato

### Sintomo

I traceback di eccezione all'interno del subprocess worker **non vengono conservati da nessuna parte**. stdout/stderr non viene instradato al processo padre, e la configurazione del logger non viene ereditata (una caratteristica di spawn).

### Soluzione

Allegare un **handler di logging dedicato** all'inizio di `worker_main`:

```python
def _configure_worker_logging() -> None:
    log_path = project_root / "logs" / "inference_worker.log"
    handler = RotatingFileHandler(log_path, maxBytes=2*1024*1024, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] (%(name)s pid=%(process)d) %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
```

Inoltre, avvolgere tutto `worker_main` con `try/except BaseException: logger.critical(traceback.format_exc())` per catturare anche gli errori in fase di importazione.

**Commit di correzione**: `cf49a42a2`

### Lezioni Apprese

- `multiprocessing.get_context("spawn").Process` non eredita la configurazione di logging del padre. **Configurarla esplicitamente sul lato generato**.
- Le eccezioni nei thread daemon vengono anche inghiottite silenziosamente per impostazione predefinita (comportamento predefinito di `threading.Thread`). Aggiungere try/except + log anche nei control daemon.

---

## 6. Il timeout inter-token di bridge.iter_stream è troppo corto per cold_load

### Sintomo

Al primo chat appare `[WARN] Stream timeout for task ...` nel log, e SSE termina prima che arrivino i token.

### Causa Radice

Il timeout di `queue.get` in `bridge.iter_stream` era **fisso a 10 secondi**, quindi il primo token non arriva durante cold_load (71 secondi), causando un timeout.

### Soluzione

Seguendo la politica dalla spec §3.4:

- `first_token_timeout = 120.0` (cold_load 71s + 50s di margine)
- `inter_token_timeout = 30.0` (intervallo massimo tra token)
- Passare a timeout breve dopo aver ricevuto il primo token

**Commit di correzione**: `35d556150`

---

## 7. handler_hailo_llm salta la normalizzazione del Prompt, causando HailoRT InvalidOperation

### Sintomo

`HailoRTInvalidOperationException` al secondo e successivi invii di chat. Log HailoRT:

```
[HailoRT] [error] CHECK failed - System role messages can only be provided on the first prompt
```

### Causa Radice

Il handler del subprocess passava i messaggi grezzi direttamente a `llm.generate(prompt=messages)`, saltando il pre-processing di `HailoLLM._prepare_prompt` nel processo interno:

- Mancava l'appiattimento del contenuto strutturato `[{"type":"text","text":"..."}]` → string semplice
- Mancava la rimozione del ruolo sistema durante la continuazione del contesto (dal turno 2 in poi)

Il template di chat di HailoRT presuppone queste due trasformazioni.

### Soluzione

Condividere `_normalise_prompt` tramite import comune + rimozione del ruolo sistema durante la continuazione del contesto:

```python
normalised = _normalise_prompt(messages)
if llm_instance.get_context_usage_size() > 0:
    normalised = [m for m in normalised if m.get("role") != "system"]
```

**Commit di correzione**: `cdd9e26fe`

### Lezioni Apprese

- Quando si implementano sia percorsi in-process che subprocess, confermare in fase di progettazione che il pre/post-processing eseguito sul lato in-process sia **applicato ugualmente su entrambi i percorsi**. Come con la contromisura di divisione dello stato padre-figlio del device_manager nella spec §3.5, è preferibile estrarlo in una libreria condivisa.

---

## 8. L'annullamento durante cold_load è ritardato da una race condition

### Sintomo (Latente)

Durante cold_load (71s), l'estensione C di HailoRT mantiene il GIL, impedendo al thread del control daemon del worker di essere eseguito. Di conseguenza, `ControlMessage(op="cancel")` da una disconnessione utente non viene elaborato. Se `generate()` viene chiamato immediatamente dopo il completamento di cold_load, la generazione di token inizia per un task abbandonato.

### Soluzione

Dopo il completamento di `acquire_genai()`, attendere 50ms → dare al control daemon il tempo di elaborare le annullamenti in sospeso → verificare `cancel_flags[task_id]` → se True, saltare generate():

```python
import time as _time
_time.sleep(0.05)
if cancel_flags.get(task_id, False):
    _emit_terminal(queue, task_id, seq, error="cancelled")
    return InferenceResult(task_id=task_id, status=TaskStatus.CANCELLED, error="cancelled")
```

**Commit di correzione**: `5fbb02d95`

---

## 9. Nessun percorso di codice in produzione chiama inference_worker.start()

### Sintomo

Anche con `hailo_genai.llm_subprocess: true` nella configurazione, l'invio di un messaggio di chat risulta in `RuntimeError("Failed to submit LLM task to worker")`.

### Causa Radice

Solo `bind_event_loop(loop)` veniva eseguito in `@app.before_serving`; la chiamata critica a `inference_bridge.start(db_path, config)` **non esisteva in produzione**. Il processo worker non veniva mai generato.

### Soluzione

Eseguire `start()` → `bind_event_loop()` nell'ordine in `@app.before_serving`, e `stop()` in `@app.after_serving`:

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

**Commit di correzione**: `9053f2f72`

---

## Elenco Completo delle Correzioni (Cronologico)

| Commit | Descrizione |
|--------|-------------|
| `9053f2f72` | Chiamare inference_bridge.start() in app.before_serving |
| `cf49a42a2` | Diagnostica di logging del worker + daemon=False + mantenimento di db_path per auto-riavvio |
| `af19f16de` | Correggere il timeout della coda in continue |
| `35d556150` | iter_stream first_token_timeout 120s, inter_token 30s |
| `d450297c2` | Introdurre il commento keepalive SSE |
| `cdd9e26fe` | Aggiungere la normalizzazione del prompt al handler |
| `213b9c962` | Intervallo keepalive 15s → 5s + log di diagnostica |
| `dff60989c` | Convertire keepalive da `: comment` → evento `data:` |
| `b35ed46cc` | **Disabilitare Quart RESPONSE_TIMEOUT 60s per SSE (correzione della causa radice)** |
| `5fbb02d95` | Verifica anticipata dell'annullamento dopo cold_load |

---

## Documenti Correlati

- Spec principale: `docs/superpowers/specs/2026-05-17-hailo-llm-subprocess-gil-unblock-design.md`
- Correlato (REJECTED): `docs/superpowers/specs/2026-05-17-hailo-subprocess-isolation-design.md`
- CMA leak: `docs/ja/hailo/HAILO_CMA_LEAK_HAILORT_5_3_0.md`
- VDevice sharing: `docs/ja/hailo/VDEVICE_SHARING_PATTERN.md`
