# Hailo LLM Subprocess GIL Unblock — Diário de Desenvolvimento da Implementação

- **Alvo**: Resolução do problema em que o event loop do Quart congela devido ao GIL durante o cold_load (~71 segundos) do binding Python do HailoRT
- **Método**: Isolamento da inferência de chat LLM em um subprocess sob `core/inference_worker/`
- **spec**: `docs/superpowers/specs/2026-05-17-hailo-llm-subprocess-gil-unblock-design.md`
- **Fases concluídas**: 0a / 0b / 1 (verificadas em hardware real)

Este documento resume as falhas não óbvias e as soluções encontradas durante a implementação. A queda de SSE em 60 segundos em particular exigiu um tempo de investigação considerável, por isso está documentada aqui para evitar que outros caiam na mesma armadilha.

---

## 1. SSE sempre cai aos 60 segundos ("Stream interrupted: network error")

### Sintoma

A resposta SSE de `/ext/hailo-genai/api/chat/send` resulta em uma **desconexão TCP exatamente aos 60 segundos**, independentemente de cold_load estar em andamento ou tokens sendo gerados.

- Navegador: `Stream interrupted: network error`
- curl: `curl: (18) transfer closed with outstanding read data remaining`
- Log de acesso: `POST ... 1.1 - - 60236944` (status `-`, duração 60,2 segundos)

Mesmo quando os dados fluem continuamente (ex.: 30 tok/s), a conexão é interrompida — portanto, não é um idle timeout.

### Isolamento

1. **Cai também no loopback local** (`http://127.0.0.1:5000/...` com curl no Pi) → não é um problema de rede intermediária, mas do lado do Pi
2. **Origem do FIN confirmada via Wireshark** — FIN enviado de 192.168.50.4 (Pi) → 192.168.50.247 (cliente) em `connection_start + 60.006s`. **Confirmado como origem do lado do Pi**
3. Nenhum dos timeouts documentados do Hypercorn (`keep_alive_timeout=5s`, `read_timeout=None`, `shutdown_timeout=60s`, etc.) se aplica a respostas ativas

### Causa Raiz

**A configuração `RESPONSE_TIMEOUT` do Quart (padrão de 60 segundos)**

`quart/asgi.py:117`:

```python
timeout = self.app.config["RESPONSE_TIMEOUT"]   # default 60
try:
    await asyncio.wait_for(self._send_response(send, response), timeout=timeout)
except asyncio.TimeoutError:
    pass   # ← após 60s, o envio da resposta é abortado → TCP close
```

A configuração padrão não antecipa respostas SSE / streaming de longa duração. `RESPONSE_TIMEOUT=60` foi projetado para prevenir APIs não-streaming descontroladas, mas é fatal para SSE.

### Solução

Definir uma **substituição de timeout por resposta** no objeto `Response` do Quart:

```python
resp = Response(
    sse_generator(),
    mimetype="text/event-stream",
    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
)
resp.timeout = None  # disable RESPONSE_TIMEOUT for SSE
return resp
```

O valor padrão de `Response.timeout` é `Ellipsis`, e `app.config["RESPONSE_TIMEOUT"]` só é usado quando o valor é `Ellipsis` (`asgi.py:112-115`). Definir explicitamente `None` desativa o timeout completamente.

**Commit de correção**: `b35ed46cc`

Locais aplicados:
- `extensions/builtin_hailo_genai/hailo_chat_routes_send.py` — chat SSE
- `extensions/builtin_hailo_genai/hailo_llm_routes.py` — `/api/llm/generate` SSE
- `extensions/builtin_hailo_genai/openai_chat_stream.py` — streaming compatível com OpenAI (×2)

As rotas não-SSE não são tocadas (o timeout de 60 segundos é útil como mecanismo de proteção lá).

### Lições Aprendidas

- **O `RESPONSE_TIMEOUT` do Quart é fatal para SSE**. Ao adicionar um novo endpoint SSE, sempre definir `resp.timeout = None`.
- Quando "os dados fluem mas a conexão cai", não suspeitar de um idle timeout. Suspeitar de uma duração máxima fixa.
- A forma mais rápida de isolar é **verificar o IP de origem do FIN no Wireshark**. Com tcpdump, o filtro `tcp[tcpflags] & tcp-fin != 0` também funciona.

---

## 2. Keepalive SSE durante cold_load (Medida preventiva independente do problema dos 60 segundos)

### Prevenção de Sintomas

Mesmo após desabilitar `RESPONSE_TIMEOUT`, ainda existe a possibilidade separada de que **redes intermediárias (roteadores domésticos / firewalls / APIs stream do navegador)** cortem conexões idle de longa duração. Os ~71 segundos de silêncio durante cold_load podem ser julgados como "mortos" por dispositivos intermediários.

### Contramedida

Envolver `HailoLLMSubprocessClient.stream()` com `stream_with_keepalive()` para enviar **eventos de dados keepalive a cada 5 segundos**:

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
                    yield ("ping", None)   # keepalive após 5s de silêncio
```

Quando a rota recebe `("ping", None)`, emite `data: {"keepalive": true}\n\n`. O cliente (chat UI) ignora silenciosamente eventos que não correspondem a `d.token` / `d.error` / `d.done`.

### Por que usar eventos `data:` em vez de comentários SSE (`: keepalive`)

Inicialmente foi tentado `: keepalive\n\n` (comentário SSE), mas se mostrou ineficaz no ambiente de teste. A mudança para `data: {"keepalive":true}` (evento de dados real) resolveu o problema. Embora comentários SSE sejam válidos segundo a especificação, alguns dispositivos intermediários e implementações de navegadores tratam linhas de comentário como "metadados ignoráveis" e ainda julgam a conexão como idle quando nenhum dado real chega. Eventos reais são mais universalmente compatíveis.

**Commits de correção**: `d450297c2`, `213b9c962`, `dff60989c`

---

## 3. O Subprocess do Worker encerra imediatamente após a inicialização em um loop

### Sintoma

`logs/inference_worker.log`:

```
22:46:29 Inference worker started (pid=1612)
22:46:31 Inference worker shutting down   ← encerramento normal após 2 segundos
22:46:32 Inference worker started (pid=1615)
22:46:34 Inference worker shutting down
...
22:46:41 Worker crashed and max restarts exhausted
```

O worker inicia, "encerra limpo" após 2 segundos, o processo pai detecta `is_alive=False` → reinicia 3 vezes e desiste; o pool de auto-reinício está esgotado.

### Causa Raiz

O loop principal de `worker_process.worker_main`:

```python
while True:
    task = queue.get_task(timeout=2.0)
    if task is None or isinstance(task, ShutdownSentinel):   # ← bug
        logger.info("Inference worker shutting down")
        break
```

`get_task(timeout=2.0)` retorna `None` quando nenhuma task está disponível. Isso era tratado da mesma forma que `ShutdownSentinel`, causando um break. O worker espera 2 segundos por uma task → a obtenção falha, retorna `None` → mal interpretado como "comando de shutdown" → break → o pai detecta `is_alive=False` → loop de reinício.

### Solução

```python
if task is None:
    continue                            # timeout → continuar o polling
if isinstance(task, ShutdownSentinel):
    break                                # break apenas em shutdown explícito
```

**Commit de correção**: `af19f16de`

### Lições Aprendidas

- `None` de `multiprocessing.Queue.get(timeout=...)` significa "timeout", não "fim da fila". "Fim da fila" deve ser expresso usando um sentinel explícito como `ShutdownSentinel`. Não confundir os dois.

---

## 4. O Worker não consegue iniciar o Subprocess interno do hailo_platform porque daemon=True

### Sintoma

Log `Worker crashed` no primeiro chat em hardware real. Causa desconhecida porque não há captura de stderr.

### Hipótese de Causa Raiz

`bridge.start()`:

```python
self._process = ctx.Process(
    target=worker_main,
    args=(...),
    daemon=True,                    # ← problema
    ...
)
```

`multiprocessing.Process(daemon=True)` mata automaticamente os filhos quando o pai encerra, mas **processos daemon não podem spawnar seus próprios processos filhos** (`AssertionError: daemonic processes are not allowed to have children`). Falha se o HailoRT iniciar internamente qualquer processo ou thread auxiliar.

### Solução

```python
daemon=False
```

Em vez disso, chamar explicitamente `inference_bridge.stop(timeout=5.0)` em `@app.after_serving` para um encerramento limpo.

**Commit de correção**: `cf49a42a2` (combinado com a adição de diagnósticos de logging do worker)

### Lições Aprendidas

- Subprocesses usando bibliotecas baseadas em extensões C como HailoRT devem usar `daemon=False`.
- A limpeza de subprocesses deve ser feita explicitamente em `@app.after_serving`.

---

## 5. A saída stderr / logger do Subprocess do Worker gerado não é capturada

### Sintoma

Tracebacks de exceção dentro do subprocess do worker **não são preservados em lugar nenhum**. stdout/stderr não é roteado para o processo pai, e a configuração do logger não é herdada (uma característica do spawn).

### Solução

Anexar um **handler de logging dedicado** no início de `worker_main`:

```python
def _configure_worker_logging() -> None:
    log_path = project_root / "logs" / "inference_worker.log"
    handler = RotatingFileHandler(log_path, maxBytes=2*1024*1024, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] (%(name)s pid=%(process)d) %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
```

Adicionalmente, envolver todo `worker_main` com `try/except BaseException: logger.critical(traceback.format_exc())` para capturar também erros em tempo de importação.

**Commit de correção**: `cf49a42a2`

### Lições Aprendidas

- `multiprocessing.get_context("spawn").Process` não herda a configuração de logging do pai. **Configurá-la explicitamente no lado gerado**.
- Exceções em threads daemon também são engolidas silenciosamente por padrão (comportamento padrão de `threading.Thread`). Adicionar try/except + log também em control daemons.

---

## 6. O timeout inter-token de bridge.iter_stream é muito curto para cold_load

### Sintoma

No primeiro chat, `[WARN] Stream timeout for task ...` aparece no log, e o SSE termina antes que os tokens cheguem.

### Causa Raiz

O timeout de `queue.get` em `bridge.iter_stream` estava **fixo em 10 segundos**, de modo que o primeiro token não chega durante cold_load (71 segundos), causando um timeout.

### Solução

Seguindo a política da spec §3.4:

- `first_token_timeout = 120.0` (cold_load 71s + 50s de margem)
- `inter_token_timeout = 30.0` (intervalo máximo entre tokens)
- Mudar para timeout curto após receber o primeiro token

**Commit de correção**: `35d556150`

---

## 7. handler_hailo_llm pula a normalização do Prompt, causando HailoRT InvalidOperation

### Sintoma

`HailoRTInvalidOperationException` no segundo e subsequentes envios de chat. Log do HailoRT:

```
[HailoRT] [error] CHECK failed - System role messages can only be provided on the first prompt
```

### Causa Raiz

O handler do subprocess passava as mensagens brutas diretamente para `llm.generate(prompt=messages)`, pulando o pré-processamento de `HailoLLM._prepare_prompt` no processo interno:

- Faltava o achatamento do conteúdo estruturado `[{"type":"text","text":"..."}]` → string simples
- Faltava a remoção do papel do sistema ao continuar o contexto (a partir do turno 2)

O template de chat do HailoRT pressupõe essas duas transformações.

### Solução

Compartilhar `_normalise_prompt` via import comum + remover o papel do sistema ao continuar o contexto:

```python
normalised = _normalise_prompt(messages)
if llm_instance.get_context_usage_size() > 0:
    normalised = [m for m in normalised if m.get("role") != "system"]
```

**Commit de correção**: `cdd9e26fe`

### Lições Aprendidas

- Ao implementar tanto caminhos in-process quanto subprocess, confirmar no momento do design que o pré/pós-processamento realizado no lado in-process seja **aplicado igualmente em ambos os caminhos**. Assim como com a contramedida de divisão de estado pai-filho do device_manager na spec §3.5, é preferível extraí-lo em uma biblioteca compartilhada.

---

## 8. O cancelamento durante cold_load é atrasado por uma condição de corrida

### Sintoma (Latente)

Durante cold_load (71s), a extensão C do HailoRT mantém o GIL, impedindo que o thread do control daemon do worker seja executado. Como resultado, `ControlMessage(op="cancel")` de uma desconexão de usuário não é processado. Se `generate()` for chamado imediatamente após o término de cold_load, a geração de tokens começa para uma task abandonada.

### Solução

Após o término de `acquire_genai()`, aguardar 50ms → dar ao control daemon tempo para processar os cancelamentos pendentes → verificar `cancel_flags[task_id]` → se True, pular generate():

```python
import time as _time
_time.sleep(0.05)
if cancel_flags.get(task_id, False):
    _emit_terminal(queue, task_id, seq, error="cancelled")
    return InferenceResult(task_id=task_id, status=TaskStatus.CANCELLED, error="cancelled")
```

**Commit de correção**: `5fbb02d95`

---

## 9. Não existe nenhum caminho de código em produção que chame inference_worker.start()

### Sintoma

Mesmo com `hailo_genai.llm_subprocess: true` na configuração, enviar uma mensagem de chat resulta em `RuntimeError("Failed to submit LLM task to worker")`.

### Causa Raiz

Apenas `bind_event_loop(loop)` estava sendo executado em `@app.before_serving`; a chamada crítica a `inference_bridge.start(db_path, config)` **não existia em produção**. O processo worker nunca foi gerado.

### Solução

Executar `start()` → `bind_event_loop()` na ordem em `@app.before_serving`, e `stop()` em `@app.after_serving`:

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

**Commit de correção**: `9053f2f72`

---

## Lista Completa de Correções (Cronológica)

| Commit | Descrição |
|--------|-----------|
| `9053f2f72` | Chamar inference_bridge.start() em app.before_serving |
| `cf49a42a2` | Diagnósticos de logging do worker + daemon=False + retenção de db_path para auto-reinício |
| `af19f16de` | Corrigir timeout da fila para continue |
| `35d556150` | iter_stream first_token_timeout 120s, inter_token 30s |
| `d450297c2` | Introduzir comentário keepalive SSE |
| `cdd9e26fe` | Adicionar normalização de prompt ao handler |
| `213b9c962` | Intervalo keepalive 15s → 5s + logs de diagnóstico |
| `dff60989c` | Converter keepalive de `: comment` → evento `data:` |
| `b35ed46cc` | **Desabilitar Quart RESPONSE_TIMEOUT 60s para SSE (correção da causa raiz)** |
| `5fbb02d95` | Verificação antecipada de cancelamento após cold_load |

---

## Documentos Relacionados

- Spec principal: `docs/superpowers/specs/2026-05-17-hailo-llm-subprocess-gil-unblock-design.md`
- Relacionado (REJECTED): `docs/superpowers/specs/2026-05-17-hailo-subprocess-isolation-design.md`
- CMA leak: `docs/ja/hailo/HAILO_CMA_LEAK_HAILORT_5_3_0.md`
- VDevice sharing: `docs/ja/hailo/VDEVICE_SHARING_PATTERN.md`
