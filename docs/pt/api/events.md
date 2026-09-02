# API de Eventos (SSE)

Entrega de eventos em tempo real via Server-Sent Events.

## GET /api/events/stream

O fluxo principal de eventos. Todas as páginas compartilham uma única conexão.

### Conectando

```javascript
// De um módulo TypeScript
import { sseSubscribe } from '../sse';
sseSubscribe('scan.complete', (data) => { ... });

// De um script inline de template
window.sseSubscribe('scan.complete', (data) => { ... });
```

**Importante**: Não use `new EventSource()` diretamente. `window.EventSource` é sobrescrito por um Proxy, então o uso direto causa erros.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `types` | string | Tipos de evento para se inscrever (separados por vírgula; omita para todos os eventos) |

### Limites de Conexão

- Até 10 conexões simultâneas por IP
- Com reconhecimento de visibilidade: a conexão entra em estado reduzido quando a aba fica oculta
- Reconexão automática com backoff exponencial

## Tipos de Evento

### Scan

| Evento | Dados | Descrição |
|-------|------|-------------|
| `scan.progress` | `{ scanned, total, current_file }` | Progresso do scan |
| `scan.complete` | `{ added_count, updated_count, added_ids?, updated_ids? }` | Scan completo |
| `config.scan_roots_changed` | `{}` | Notificação de mudança de raiz de scan |

### Favoritos & Coleções

| Evento | Dados | Descrição |
|-------|------|-------------|
| `favorite.add` | `{ file_id, collection_id }` | Favorito adicionado |
| `favorite.remove` | `{ file_id, collection_id }` | Favorito removido |
| `collection.create` | `{ id, name }` | Coleção criada |
| `collection.delete` | `{ id }` | Coleção deletada |

### Análise de IA & Tagging

| Evento | Dados | Descrição |
|-------|------|-------------|
| `semantic_index.start` | `{ total }` | Indexação CLIP iniciada |
| `semantic_index.progress` | `{ done, total }` | Progresso de indexação CLIP |
| `semantic_index.complete` | `{ indexed }` | Indexação CLIP completa |
| `vlm_caption.start` | `{ total }` | Legendagem VLM iniciada |
| `vlm_caption.progress` | `{ done, total }` | Progresso de legendagem VLM |
| `vlm_caption.complete` | `{ processed }` | Legendagem VLM completa |
| `yolo_detect.start` | `{ total }` | Detecção YOLO iniciada |
| `yolo_detect.progress` | `{ done, total }` | Progresso de detecção YOLO |
| `yolo_detect.complete` | `{ detected }` | Detecção YOLO completa |

### Freeze & Pull-back

| Evento | Dados | Descrição |
|-------|------|-------------|
| `fpb.start` | `{ job_id }` | Trabalho iniciado |
| `fpb.progress` | `{ job_id, frame, total }` | Progresso de frame |
| `fpb.complete` | `{ job_id, output_path }` | Trabalho completo |
| `fpb.error` | `{ job_id, error }` | Erro de trabalho |

### Logs de Chat

| Evento | Dados | Descrição |
|-------|------|-------------|
| `chatlog_reprocess.start` | `{ total }` | Reprocessamento de IA iniciado |
| `chatlog_reprocess.progress` | `{ done, total }` | Progresso de reprocessamento de IA |
| `chatlog_reprocess.complete` | `{ processed }` | Reprocessamento de IA completo |
| `chatlog_reprocess.error` | `{ error }` | Erro de reprocessamento de IA |

### Agendador

| Evento | Dados | Descrição |
|-------|------|-------------|
| `scheduler.job_executed` | `{ job_id, result }` | Trabalho agendado completo com sucesso |
| `scheduler.job_error` | `{ job_id, error }` | Falha de trabalho agendado |

## GET /api/logs/stream

Um fluxo SSE dedicado para logs de servidor. Funciona independentemente do fluxo principal.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `level` | string | Nível de log mínimo (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

### Eventos

| Evento | Dados | Descrição |
|-------|------|-------------|
| `log.entry` | `{ seq, ts, level, name, message }` | Entrada de log |

### Limites de Conexão

- Até 3 conexões simultâneas por IP (separadas do fluxo principal)
- Intervalo de heartbeat de 15 segundos (`: heartbeat\n\n`)
