# Hailo LLM Subprocess GIL Unblock — Implementierungs-Devlog

- **Ziel**: Behebung des Problems, bei dem der Quart-Event-Loop während des cold_load (~71 Sekunden) des HailoRT-Python-Bindings durch den GIL blockiert wird
- **Methode**: Isolierung der LLM-Chat-Inferenz in einen Subprocess unter `core/inference_worker/`
- **spec**: `docs/superpowers/specs/2026-05-17-hailo-llm-subprocess-gil-unblock-design.md`
- **Abgeschlossene Phasen**: 0a / 0b / 1 (auf echter Hardware verifiziert)

Dieses Dokument fasst nicht offensichtliche Fehler und Lösungen zusammen, die während der Implementierung aufgetreten sind. Insbesondere der SSE-60-Sekunden-Drop erforderte erhebliche Untersuchungszeit, weshalb er hier dokumentiert wird, um zu verhindern, dass andere in dieselbe Falle tappen.

---

## 1. SSE trennt immer nach 60 Sekunden ("Stream interrupted: network error")

### Symptom

Die SSE-Antwort von `/ext/hailo-genai/api/chat/send` führt zu einer **TCP-Trennung genau nach 60 Sekunden**, unabhängig davon, ob cold_load läuft oder Tokens generiert werden.

- Browser: `Stream interrupted: network error`
- curl: `curl: (18) transfer closed with outstanding read data remaining`
- Zugriffsprotokoll: `POST ... 1.1 - - 60236944` (Status `-`, Dauer 60,2 Sekunden)

Selbst wenn Daten kontinuierlich fließen (z.B. 30 tok/s), wird die Verbindung getrennt — es handelt sich also nicht um einen Idle-Timeout.

### Eingrenzung

1. **Trennt auch über lokalen Loopback** (`http://127.0.0.1:5000/...` auf dem Pi mit curl) → kein Problem im Zwischennetzwerk, sondern auf der Pi-Seite
2. **FIN-Ursprung mit Wireshark bestätigt** — FIN von 192.168.50.4 (Pi) → 192.168.50.247 (Client) wird bei `connection_start + 60.006s` gesendet. **Pi-seitiger Ursprung bestätigt**
3. Keiner der dokumentierten Hypercorn-Timeouts (`keep_alive_timeout=5s`, `read_timeout=None`, `shutdown_timeout=60s` usw.) gilt für aktive Antworten

### Grundursache

**Quarts `RESPONSE_TIMEOUT`-Einstellung (Standard 60 Sekunden)**

`quart/asgi.py:117`:

```python
timeout = self.app.config["RESPONSE_TIMEOUT"]   # default 60
try:
    await asyncio.wait_for(self._send_response(send, response), timeout=timeout)
except asyncio.TimeoutError:
    pass   # ← nach 60s wird das Senden der Antwort abgebrochen → TCP close
```

Die Standardeinstellung berücksichtigt keine lang andauernden SSE-/Streaming-Antworten. `RESPONSE_TIMEOUT=60` soll außer Kontrolle geratene Nicht-Streaming-APIs verhindern, ist aber für SSE fatal.

### Lösung

**Pro-Response-Timeout-Überschreibung** am Quart-`Response`-Objekt setzen:

```python
resp = Response(
    sse_generator(),
    mimetype="text/event-stream",
    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
)
resp.timeout = None  # disable RESPONSE_TIMEOUT for SSE
return resp
```

Der Standardwert von `Response.timeout` ist `Ellipsis`, und `app.config["RESPONSE_TIMEOUT"]` wird nur verwendet, wenn der Wert `Ellipsis` ist (`asgi.py:112-115`). Das explizite Setzen von `None` deaktiviert den Timeout vollständig.

**Fix-Commit**: `b35ed46cc`

Angewendete Stellen:
- `extensions/builtin_hailo_genai/hailo_chat_routes_send.py` — Chat-SSE
- `extensions/builtin_hailo_genai/hailo_llm_routes.py` — `/api/llm/generate` SSE
- `extensions/builtin_hailo_genai/openai_chat_stream.py` — OpenAI-kompatibles Streaming (×2)

Nicht-SSE-Routen werden nicht angefasst (der 60-Sekunden-Timeout ist dort als Schutzmechanismus nützlich).

### Erkenntnisse

- **Quarts `RESPONSE_TIMEOUT` ist für SSE fatal**. Beim Hinzufügen eines neuen SSE-Endpunkts immer `resp.timeout = None` setzen.
- Wenn "Daten fließen, aber die Verbindung wird getrennt", keinen Idle-Timeout vermuten. Eine feste Maximaldauer vermuten.
- Die schnellste Eingrenzung ist es, **die FIN-Ursprungs-IP in Wireshark zu prüfen**. Mit tcpdump funktioniert auch der Filter `tcp[tcpflags] & tcp-fin != 0`.

---

## 2. SSE-Keepalive während cold_load (Präventivmaßnahme unabhängig vom 60-Sekunden-Problem)

### Symptomprävention

Selbst nach der Deaktivierung von `RESPONSE_TIMEOUT` besteht weiterhin die separate Möglichkeit, dass **Zwischennetzwerke (Consumer-Router / Firewalls / Browser-Stream-APIs)** lang andauernde Idle-Verbindungen trennen. Die ~71 Sekunden Stille während cold_load können von Zwischengeräten als "tot" eingestuft werden.

### Gegenmaßnahme

`HailoLLMSubprocessClient.stream()` mit `stream_with_keepalive()` umhüllen, um **Keepalive-Datenereignisse im 5-Sekunden-Takt** zu senden:

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
                    yield ("ping", None)   # Keepalive nach 5s Stille
```

Wenn die Route `("ping", None)` empfängt, wird `data: {"keepalive": true}\n\n` gesendet. Der Client (Chat-UI) ignoriert Ereignisse, die nicht `d.token` / `d.error` / `d.done` entsprechen, stillschweigend.

### Warum `data:`-Ereignisse statt SSE-Kommentare (`: keepalive`)

Zunächst wurde `: keepalive\n\n` (SSE-Kommentar) versucht, war aber in der Testumgebung wirkungslos. Der Wechsel zu `data: {"keepalive":true}` (echtes Datenereignis) löste das Problem. Obwohl SSE-Kommentare laut Spezifikation gültig sind, behandeln einige Zwischengeräte und Browser-Implementierungen Kommentarzeilen als "ignorierbares Metadaten" und bewerten die Verbindung trotzdem als idle, wenn keine echten Daten ankommen. Echte Ereignisse sind universell kompatibler.

**Fix-Commits**: `d450297c2`, `213b9c962`, `dff60989c`

---

## 3. Worker-Subprocess beendet sich unmittelbar nach dem Start in einer Schleife

### Symptom

`logs/inference_worker.log`:

```
22:46:29 Inference worker started (pid=1612)
22:46:31 Inference worker shutting down   ← normales Beenden nach 2 Sekunden
22:46:32 Inference worker started (pid=1615)
22:46:34 Inference worker shutting down
...
22:46:41 Worker crashed and max restarts exhausted
```

Der Worker startet, "fährt sauber herunter" nach 2 Sekunden, der Elternprozess erkennt `is_alive=False` → startet 3-mal neu und gibt auf; der Auto-Restart-Pool ist erschöpft.

### Grundursache

Die Hauptschleife von `worker_process.worker_main`:

```python
while True:
    task = queue.get_task(timeout=2.0)
    if task is None or isinstance(task, ShutdownSentinel):   # ← bug
        logger.info("Inference worker shutting down")
        break
```

`get_task(timeout=2.0)` gibt `None` zurück, wenn keine Task verfügbar ist. Dies wurde fälschlicherweise wie `ShutdownSentinel` behandelt und führte zu einem break. Der Worker wartet 2 Sekunden auf eine Task → Abruf schlägt fehl, gibt `None` zurück → als "Shutdown-Befehl" fehlinterpretiert → break → Elternprozess erkennt `is_alive=False` → Neustart-Schleife.

### Lösung

```python
if task is None:
    continue                            # Timeout → Polling fortsetzen
if isinstance(task, ShutdownSentinel):
    break                                # Nur bei explizitem Shutdown breaken
```

**Fix-Commit**: `af19f16de`

### Erkenntnisse

- `None` von `multiprocessing.Queue.get(timeout=...)` bedeutet "Timeout", nicht "Ende der Queue". "Ende der Queue" sollte durch einen expliziten Sentinel wie `ShutdownSentinel` ausgedrückt werden. Beide nicht verwechseln.

---

## 4. Worker kann keinen internen hailo_platform-Subprocess starten, weil daemon=True gesetzt ist

### Symptom

`Worker crashed`-Protokoll beim ersten Chat auf echter Hardware. Ursache unbekannt, da keine stderr-Erfassung vorhanden.

### Grundursachen-Hypothese

`bridge.start()`:

```python
self._process = ctx.Process(
    target=worker_main,
    args=(...),
    daemon=True,                    # ← Problem
    ...
)
```

`multiprocessing.Process(daemon=True)` beendet Kindprozesse automatisch, wenn der Elternprozess beendet wird, aber **daemonische Prozesse können keine eigenen Kindprozesse spawnen** (`AssertionError: daemonic processes are not allowed to have children`). Falls HailoRT intern irgendeinen Helper-Prozess oder -Thread startet, schlägt dies fehl.

### Lösung

```python
daemon=False
```

Stattdessen `inference_bridge.stop(timeout=5.0)` explizit in `@app.after_serving` aufrufen für sauberes Herunterfahren.

**Fix-Commit**: `cf49a42a2` (zusammen mit Worker-Logging-Diagnostik-Ergänzung)

### Erkenntnisse

- Subprocesses, die C-Erweiterungsbibliotheken wie HailoRT verwenden, sollten `daemon=False` setzen.
- Subprocess-Bereinigung sollte explizit in `@app.after_serving` erfolgen.

---

## 5. stderr / Logger-Ausgabe des gespawnten Worker-Subprocesses wird nicht erfasst

### Symptom

Ausnahme-Tracebacks im Worker-Subprocess **bleiben nirgendwo erhalten**. stdout/stderr wird nicht an den Elternprozess weitergeleitet, und die Logger-Konfiguration wird nicht vererbt (Eigenschaft von spawn).

### Lösung

Am Anfang von `worker_main` einen **dedizierten Logging-Handler** anhängen:

```python
def _configure_worker_logging() -> None:
    log_path = project_root / "logs" / "inference_worker.log"
    handler = RotatingFileHandler(log_path, maxBytes=2*1024*1024, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] (%(name)s pid=%(process)d) %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
```

Zusätzlich das gesamte `worker_main` mit `try/except BaseException: logger.critical(traceback.format_exc())` umhüllen, um auch Import-Zeit-Fehler zu erfassen.

**Fix-Commit**: `cf49a42a2`

### Erkenntnisse

- `multiprocessing.get_context("spawn").Process` erbt die Logging-Konfiguration des Elternprozesses nicht. **Auf der gespawnten Seite explizit einrichten**.
- Ausnahmen in Daemon-Threads werden standardmäßig auch stillschweigend geschluckt (`threading.Thread`-Standardverhalten). Auch in Control-Daemons try/except + log hinzufügen.

---

## 6. bridge.iter_stream-Inter-Token-Timeout ist für cold_load zu kurz

### Symptom

Beim ersten Chat erscheint `[WARN] Stream timeout for task ...` im Protokoll, und SSE endet, bevor Tokens ankommen.

### Grundursache

Der `queue.get`-Timeout in `bridge.iter_stream` war **auf 10 Sekunden festgelegt**, sodass das erste Token während cold_load (71 Sekunden) nicht rechtzeitig ankommt und ein Timeout ausgelöst wird.

### Lösung

Gemäß der Richtlinie aus spec §3.4:

- `first_token_timeout = 120.0` (cold_load 71s + 50s Puffer)
- `inter_token_timeout = 30.0` (maximales Token-Intervall)
- Nach Erhalt des ersten Tokens auf kurzen Timeout umschalten

**Fix-Commit**: `35d556150`

---

## 7. handler_hailo_llm überspringt Prompt-Normalisierung und verursacht HailoRT InvalidOperation

### Symptom

`HailoRTInvalidOperationException` beim zweiten und weiteren Chat-Sendungen. HailoRT-Protokoll:

```
[HailoRT] [error] CHECK failed - System role messages can only be provided on the first prompt
```

### Grundursache

Der Subprocess-Handler übergibt Nachrichten direkt als Rohdaten an `llm.generate(prompt=messages)` und überspringt die Vorverarbeitung von `HailoLLM._prepare_prompt` im In-Process-Pfad:

- Abflachung von strukturiertem Inhalt `[{"type":"text","text":"..."}]` → Plain-String fehlte
- Entfernung der System-Rolle bei Kontext-Fortsetzung (ab Runde 2) fehlte

HailoRTs Chat-Template setzt diese beiden Transformationen voraus.

### Lösung

`_normalise_prompt` über gemeinsamen Import + Entfernung der System-Rolle bei Kontext-Fortsetzung:

```python
normalised = _normalise_prompt(messages)
if llm_instance.get_context_usage_size() > 0:
    normalised = [m for m in normalised if m.get("role") != "system"]
```

**Fix-Commit**: `cdd9e26fe`

### Erkenntnisse

- Bei der Implementierung sowohl des In-Process- als auch des Subprocess-Pfades beim Entwurf bestätigen, dass Pre-/Post-Processing, das auf der In-Process-Seite durchgeführt wird, **auf beiden Pfaden gleichermaßen angewendet wird**. Wie bei der Device-Manager-Eltern-Kind-Zustandstrennung in spec §3.5 ist eine Auslagerung in eine gemeinsame Bibliothek vorzuziehen.

---

## 8. Cancel während cold_load ist durch eine Race-Condition verzögert

### Symptom (Latent)

Während cold_load (71s) hält die HailoRT-C-Erweiterung den GIL, sodass der Control-Daemon-Thread des Workers nicht laufen kann. Daher wird `ControlMessage(op="cancel")` bei einer Benutzerverbindungsunterbrechung nicht verarbeitet. Wenn `generate()` unmittelbar nach Abschluss von cold_load aufgerufen wird, beginnt die Token-Generierung für eine aufgegebene Task.

### Lösung

Nach Abschluss von `acquire_genai()` 50ms warten → Control-Daemon Zeit geben, um ausstehende Cancels zu verarbeiten → `cancel_flags[task_id]` prüfen → wenn True, generate() überspringen:

```python
import time as _time
_time.sleep(0.05)
if cancel_flags.get(task_id, False):
    _emit_terminal(queue, task_id, seq, error="cancelled")
    return InferenceResult(task_id=task_id, status=TaskStatus.CANCELLED, error="cancelled")
```

**Fix-Commit**: `5fbb02d95`

---

## 9. Kein Produktionscode-Pfad ruft inference_worker.start() auf

### Symptom

Selbst mit `hailo_genai.llm_subprocess: true` in der Konfiguration führt das Senden einer Chat-Nachricht zu `RuntimeError("Failed to submit LLM task to worker")`.

### Grundursache

In `@app.before_serving` wurde nur `bind_event_loop(loop)` ausgeführt; der entscheidende Aufruf von `inference_bridge.start(db_path, config)` **existierte nicht in der Produktion**. Der Worker-Prozess wurde nie gespawnt.

### Lösung

`start()` → `bind_event_loop()` in `@app.before_serving` der Reihe nach ausführen, `stop()` in `@app.after_serving`:

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

**Fix-Commit**: `9053f2f72`

---

## Vollständige Korrekturen-Liste (Chronologisch)

| Commit | Inhalt |
|--------|--------|
| `9053f2f72` | inference_bridge.start() in app.before_serving aufrufen |
| `cf49a42a2` | Worker-Logging-Diagnostik + daemon=False + db_path-Beibehaltung für Auto-Restart |
| `af19f16de` | Queue-Timeout zu continue korrigieren |
| `35d556150` | iter_stream first_token_timeout 120s, inter_token 30s |
| `d450297c2` | SSE-Keepalive-Kommentar einführen |
| `cdd9e26fe` | Prompt-Normalisierung zum Handler hinzufügen |
| `213b9c962` | Keepalive-Intervall 15s → 5s + Diagnose-Logs |
| `dff60989c` | Keepalive von `: comment` → `data:`-Ereignis umwandeln |
| `b35ed46cc` | **Quart RESPONSE_TIMEOUT 60s für SSE deaktivieren (Grundursachen-Fix)** |
| `5fbb02d95` | Frühzeitige Cancel-Prüfung nach cold_load |

---

## Verwandte Dokumente

- Haupt-Spec: `docs/superpowers/specs/2026-05-17-hailo-llm-subprocess-gil-unblock-design.md`
- Verwandt (REJECTED): `docs/superpowers/specs/2026-05-17-hailo-subprocess-isolation-design.md`
- CMA-Leak: `docs/ja/hailo/HAILO_CMA_LEAK_HAILORT_5_3_0.md`
- VDevice-Sharing: `docs/ja/hailo/VDEVICE_SHARING_PATTERN.md`
