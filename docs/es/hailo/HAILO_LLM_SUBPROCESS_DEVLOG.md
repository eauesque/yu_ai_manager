# Hailo LLM Subprocess GIL Unblock — Registro de Desarrollo de Implementación

- **Objetivo**: Resolución del problema en el que el event loop de Quart se congela debido al GIL durante el cold_load (~71 segundos) del binding Python de HailoRT
- **Método**: Aislamiento de la inferencia de chat LLM en un subprocess bajo `core/inference_worker/`
- **spec**: `docs/superpowers/specs/2026-05-17-hailo-llm-subprocess-gil-unblock-design.md`
- **Fases completadas**: 0a / 0b / 1 (verificadas en hardware real)

Este documento resume los fallos no obvios y las soluciones encontradas durante la implementación. La caída de SSE a los 60 segundos en particular requirió un tiempo de investigación considerable, por lo que se documenta aquí para evitar que otros caigan en la misma trampa.

---

## 1. SSE siempre se interrumpe a los 60 segundos ("Stream interrupted: network error")

### Síntoma

La respuesta SSE de `/ext/hailo-genai/api/chat/send` resulta en una **desconexión TCP exactamente a los 60 segundos**, independientemente de si cold_load está en progreso o si se están generando tokens.

- Navegador: `Stream interrupted: network error`
- curl: `curl: (18) transfer closed with outstanding read data remaining`
- Log de acceso: `POST ... 1.1 - - 60236944` (status `-`, duración 60,2 segundos)

Incluso cuando los datos fluyen continuamente (p.ej., 30 tok/s), la conexión se interrumpe — por lo que no es un idle timeout.

### Aislamiento

1. **Se interrumpe también en loopback local** (`http://127.0.0.1:5000/...` con curl en la Pi) → no es un problema de red intermedia, sino del lado de la Pi
2. **Origen de FIN confirmado con Wireshark** — FIN enviado desde 192.168.50.4 (Pi) → 192.168.50.247 (cliente) en `connection_start + 60.006s`. **Confirmado como origen del lado de la Pi**
3. Ninguno de los timeouts documentados de Hypercorn (`keep_alive_timeout=5s`, `read_timeout=None`, `shutdown_timeout=60s`, etc.) se aplica a las respuestas activas

### Causa Raíz

**La configuración `RESPONSE_TIMEOUT` de Quart (predeterminada en 60 segundos)**

`quart/asgi.py:117`:

```python
timeout = self.app.config["RESPONSE_TIMEOUT"]   # default 60
try:
    await asyncio.wait_for(self._send_response(send, response), timeout=timeout)
except asyncio.TimeoutError:
    pass   # ← después de 60s, se aborta el envío de la respuesta → TCP close
```

La configuración predeterminada no contempla respuestas SSE / streaming de larga duración. `RESPONSE_TIMEOUT=60` está diseñado para prevenir APIs no streaming descontroladas, pero es fatal para SSE.

### Solución

Establecer una **anulación de timeout por respuesta** en el objeto `Response` de Quart:

```python
resp = Response(
    sse_generator(),
    mimetype="text/event-stream",
    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
)
resp.timeout = None  # disable RESPONSE_TIMEOUT for SSE
return resp
```

El valor predeterminado de `Response.timeout` es `Ellipsis`, y `app.config["RESPONSE_TIMEOUT"]` solo se usa cuando el valor es `Ellipsis` (`asgi.py:112-115`). Establecer explícitamente `None` desactiva el timeout por completo.

**Commit de corrección**: `b35ed46cc`

Lugares aplicados:
- `extensions/builtin_hailo_genai/hailo_chat_routes_send.py` — chat SSE
- `extensions/builtin_hailo_genai/hailo_llm_routes.py` — `/api/llm/generate` SSE
- `extensions/builtin_hailo_genai/openai_chat_stream.py` — streaming compatible con OpenAI (×2)

Las rutas no SSE no se tocan (el timeout de 60 segundos es útil como mecanismo de protección allí).

### Lecciones Aprendidas

- **El `RESPONSE_TIMEOUT` de Quart es fatal para SSE**. Al agregar un nuevo endpoint SSE, siempre establecer `resp.timeout = None`.
- Cuando "los datos fluyen pero la conexión se interrumpe", no sospechar de un idle timeout. Sospechar de una duración máxima fija.
- La forma más rápida de aislar el problema es **revisar la IP de origen del FIN en Wireshark**. Con tcpdump también funciona el filtro `tcp[tcpflags] & tcp-fin != 0`.

---

## 2. Keepalive de SSE durante cold_load (Medida preventiva independiente del problema de 60 segundos)

### Prevención de Síntomas

Incluso después de deshabilitar `RESPONSE_TIMEOUT`, existe la posibilidad separada de que las **redes intermedias (routers de consumo / firewalls / APIs de stream del navegador)** corten las conexiones idle de larga duración. Los ~71 segundos de silencio durante cold_load pueden ser juzgados como "muertos" por los dispositivos intermedios.

### Contramedida

Envolver `HailoLLMSubprocessClient.stream()` con `stream_with_keepalive()` para enviar **eventos de datos keepalive cada 5 segundos**:

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
                    yield ("ping", None)   # keepalive después de 5s de silencio
```

Cuando la ruta recibe `("ping", None)`, emite `data: {"keepalive": true}\n\n`. El cliente (chat UI) ignora silenciosamente los eventos que no coinciden con `d.token` / `d.error` / `d.done`.

### Por qué usar eventos `data:` en lugar de comentarios SSE (`: keepalive`)

Inicialmente se probó `: keepalive\n\n` (comentario SSE), pero resultó ineficaz en el entorno de prueba. El cambio a `data: {"keepalive":true}` (evento de datos real) lo resolvió. Aunque los comentarios SSE son válidos según la especificación, algunos dispositivos intermedios e implementaciones de navegadores tratan las líneas de comentarios como "metadatos ignorables" y aún así juzgan la conexión como idle cuando no llegan datos reales. Los eventos reales son más universalmente compatibles.

**Commits de corrección**: `d450297c2`, `213b9c962`, `dff60989c`

---

## 3. El Subprocess del Worker se termina inmediatamente después del inicio en un bucle

### Síntoma

`logs/inference_worker.log`:

```
22:46:29 Inference worker started (pid=1612)
22:46:31 Inference worker shutting down   ← salida normal después de 2 segundos
22:46:32 Inference worker started (pid=1615)
22:46:34 Inference worker shutting down
...
22:46:41 Worker crashed and max restarts exhausted
```

El worker arranca, "se apaga limpiamente" después de 2 segundos, el proceso padre detecta `is_alive=False` → reinicia 3 veces y se rinde; el pool de auto-reinicio se agota.

### Causa Raíz

El bucle principal de `worker_process.worker_main`:

```python
while True:
    task = queue.get_task(timeout=2.0)
    if task is None or isinstance(task, ShutdownSentinel):   # ← bug
        logger.info("Inference worker shutting down")
        break
```

`get_task(timeout=2.0)` devuelve `None` cuando no hay ninguna tarea disponible. Esto se trató igual que `ShutdownSentinel`, provocando un break. El worker espera 2 segundos para una tarea → el intento falla, devuelve `None` → malinterpretado como "comando de shutdown" → break → el padre detecta `is_alive=False` → bucle de reinicio.

### Solución

```python
if task is None:
    continue                            # timeout → continuar el polling
if isinstance(task, ShutdownSentinel):
    break                                # break solo en shutdown explícito
```

**Commit de corrección**: `af19f16de`

### Lecciones Aprendidas

- `None` de `multiprocessing.Queue.get(timeout=...)` significa "timeout", no "fin de la cola". "Fin de la cola" debe expresarse usando un sentinel explícito como `ShutdownSentinel`. No confundir ambos.

---

## 4. El Worker no puede iniciar el Subprocess interno de hailo_platform porque daemon=True

### Síntoma

Log `Worker crashed` en el primer chat en hardware real. Causa desconocida porque no se captura stderr.

### Hipótesis de Causa Raíz

`bridge.start()`:

```python
self._process = ctx.Process(
    target=worker_main,
    args=(...),
    daemon=True,                    # ← problema
    ...
)
```

`multiprocessing.Process(daemon=True)` mata automáticamente a los hijos cuando el padre termina, pero **los procesos demonizados no pueden generar sus propios procesos hijos** (`AssertionError: daemonic processes are not allowed to have children`). Falla si HailoRT internamente inicia algún proceso o hilo auxiliar.

### Solución

```python
daemon=False
```

En su lugar, llamar explícitamente a `inference_bridge.stop(timeout=5.0)` en `@app.after_serving` para un apagado limpio.

**Commit de corrección**: `cf49a42a2` (combinado con la adición de diagnósticos de logging del worker)

### Lecciones Aprendidas

- Los subprocesses que usan bibliotecas basadas en extensiones C como HailoRT deben usar `daemon=False`.
- La limpieza de subprocesses debe realizarse explícitamente en `@app.after_serving`.

---

## 5. La salida de stderr / logger del Subprocess del Worker generado no se captura

### Síntoma

Los tracebacks de excepción dentro del subprocess del worker **no se conservan en ningún lugar**. stdout/stderr no se enruta al proceso padre, y la configuración del logger no se hereda (una característica de spawn).

### Solución

Adjuntar un **handler de logging dedicado** al inicio de `worker_main`:

```python
def _configure_worker_logging() -> None:
    log_path = project_root / "logs" / "inference_worker.log"
    handler = RotatingFileHandler(log_path, maxBytes=2*1024*1024, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] (%(name)s pid=%(process)d) %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
```

Adicionalmente, envolver todo `worker_main` con `try/except BaseException: logger.critical(traceback.format_exc())` para capturar también los errores en tiempo de importación.

**Commit de corrección**: `cf49a42a2`

### Lecciones Aprendidas

- `multiprocessing.get_context("spawn").Process` no hereda la configuración de logging del padre. **Configurarlo explícitamente en el lado generado**.
- Las excepciones en hilos daemon también se engullen silenciosamente por defecto (comportamiento predeterminado de `threading.Thread`). Agregar try/except + log también en los control daemons.

---

## 6. El timeout inter-token de bridge.iter_stream es demasiado corto para cold_load

### Síntoma

En el primer chat aparece `[WARN] Stream timeout for task ...` en el log, y SSE termina antes de que lleguen los tokens.

### Causa Raíz

El timeout de `queue.get` en `bridge.iter_stream` estaba **fijo en 10 segundos**, por lo que el primer token no llega durante cold_load (71 segundos), provocando un timeout.

### Solución

Siguiendo la política de la spec §3.4:

- `first_token_timeout = 120.0` (cold_load 71s + 50s de margen)
- `inter_token_timeout = 30.0` (intervalo máximo entre tokens)
- Cambiar a timeout corto después de recibir el primer token

**Commit de corrección**: `35d556150`

---

## 7. handler_hailo_llm omite la normalización del Prompt, causando HailoRT InvalidOperation

### Síntoma

`HailoRTInvalidOperationException` en el segundo y siguientes envíos de chat. Log de HailoRT:

```
[HailoRT] [error] CHECK failed - System role messages can only be provided on the first prompt
```

### Causa Raíz

El handler del subprocess pasaba los mensajes directamente como datos brutos a `llm.generate(prompt=messages)`, omitiendo el preprocesamiento de `HailoLLM._prepare_prompt` en el proceso interno:

- Faltaba el aplanamiento del contenido estructurado `[{"type":"text","text":"..."}]` → string plano
- Faltaba la eliminación del rol del sistema al continuar el contexto (desde el turno 2 en adelante)

La plantilla de chat de HailoRT asume estas dos transformaciones.

### Solución

Compartir `_normalise_prompt` mediante importación + eliminar el rol del sistema al continuar el contexto:

```python
normalised = _normalise_prompt(messages)
if llm_instance.get_context_usage_size() > 0:
    normalised = [m for m in normalised if m.get("role") != "system"]
```

**Commit de corrección**: `cdd9e26fe`

### Lecciones Aprendidas

- Al implementar tanto rutas en proceso como de subprocess, confirmar en el momento del diseño que el pre/post-procesamiento realizado en el lado en proceso se **aplica igualmente en ambas rutas**. Al igual que con la contramedida de división de estado padre-hijo del device_manager en spec §3.5, es preferible factorizarlo en una biblioteca compartida.

---

## 8. La cancelación durante cold_load se retrasa por una condición de carrera

### Síntoma (Latente)

Durante cold_load (71s), la extensión C de HailoRT mantiene el GIL, impidiendo que el hilo del control daemon del worker se ejecute. Como resultado, `ControlMessage(op="cancel")` de una desconexión de usuario no se procesa. Si se llama a `generate()` inmediatamente después de que cold_load finaliza, la generación de tokens comienza para una tarea abandonada.

### Solución

Después de que `acquire_genai()` finaliza, esperar 50ms → dar tiempo al control daemon para procesar los cancels pendientes → verificar `cancel_flags[task_id]` → si es True, omitir generate():

```python
import time as _time
_time.sleep(0.05)
if cancel_flags.get(task_id, False):
    _emit_terminal(queue, task_id, seq, error="cancelled")
    return InferenceResult(task_id=task_id, status=TaskStatus.CANCELLED, error="cancelled")
```

**Commit de corrección**: `5fbb02d95`

---

## 9. No existe ninguna ruta de código en producción que llame a inference_worker.start()

### Síntoma

Incluso con `hailo_genai.llm_subprocess: true` en la configuración, enviar un mensaje de chat resulta en `RuntimeError("Failed to submit LLM task to worker")`.

### Causa Raíz

Solo se ejecutaba `bind_event_loop(loop)` en `@app.before_serving`; la llamada crítica a `inference_bridge.start(db_path, config)` **no existía en producción**. El proceso worker nunca fue generado.

### Solución

Ejecutar `start()` → `bind_event_loop()` en orden dentro de `@app.before_serving`, y `stop()` en `@app.after_serving`:

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

**Commit de corrección**: `9053f2f72`

---

## Lista Completa de Correcciones (Cronológica)

| Commit | Descripción |
|--------|-------------|
| `9053f2f72` | Llamar a inference_bridge.start() en app.before_serving |
| `cf49a42a2` | Diagnósticos de logging del worker + daemon=False + retención de db_path para auto-reinicio |
| `af19f16de` | Corregir timeout de cola a continue |
| `35d556150` | iter_stream first_token_timeout 120s, inter_token 30s |
| `d450297c2` | Introducir comentario keepalive de SSE |
| `cdd9e26fe` | Añadir normalización de prompt al handler |
| `213b9c962` | Intervalo de keepalive 15s → 5s + logs de diagnóstico |
| `dff60989c` | Convertir keepalive de `: comment` → evento `data:` |
| `b35ed46cc` | **Deshabilitar Quart RESPONSE_TIMEOUT de 60s para SSE (corrección de la causa raíz)** |
| `5fbb02d95` | Verificación anticipada de cancel después de cold_load |

---

## Documentos Relacionados

- Spec principal: `docs/superpowers/specs/2026-05-17-hailo-llm-subprocess-gil-unblock-design.md`
- Relacionado (REJECTED): `docs/superpowers/specs/2026-05-17-hailo-subprocess-isolation-design.md`
- CMA leak: `docs/ja/hailo/HAILO_CMA_LEAK_HAILORT_5_3_0.md`
- VDevice sharing: `docs/ja/hailo/VDEVICE_SHARING_PATTERN.md`
