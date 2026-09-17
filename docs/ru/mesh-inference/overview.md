# Архитектура меш-инференса

> Целевая версия: v4.67.0 и выше

## Обзор

Система меш-инференса — механизм, при котором несколько узлов yu_ai_manager в LAN
совместно распределяют задачи инференса (tagger / clip / yolo / whisper).
Сочетает автоматическое обнаружение через mDNS, кражу работы через asyncio.Queue
и фильтры отключения для отдельных узлов — горизонтально масштабируется без конфигурации.

---

## Общая архитектура

```
┌─────────────────────────────────────────────────┐
│                 CoworkManager                   │
│  Создаёт InferenceRouter при запуске            │
│  Регистрирует в core.mesh_inference.set_router()│
└────────────────────┬────────────────────────────┘
                     │
          ┌──────────▼──────────┐
          │   InferenceRouter   │
          │                     │
          │  _local_peer        │
          │  _registry ─────────┼──► PeerRegistry (список LAN-пиров)
          │  _strategy ─────────┼──► DisableAwareStrategy
          └──────────┬──────────┘
                     │ dispatch_inference()
          ┌──────────▼──────────┐
          │   asyncio.Queue     │  work-stealing очередь
          │   item, item, ...   │
          └──┬───────────┬──────┘
             │           │
       ┌─────▼──┐   ┌────▼────┐
       │ peer A │   │ peer B  │   (параллельные воркеры)
       │(local) │   │(remote) │
       └────────┘   └─────────┘
```

---

## Типы инференса и бэкенды

| Тип инференса | Бэкенд | Назначение |
|--------------|--------|-----------|
| `tagger` | ONNX (WD14 и т.д.) / Hailo NPU | Тегирование изображений |
| `clip` | ONNX / Hailo / Remote | Вектор эмбеддинга изображения |
| `yolo` | ONNX / Hailo | Обнаружение объектов |
| `whisper` | faster-whisper / Remote | Транскрипция аудио |
| `llm` | OpenAI-compat / Ollama | LLM-инференс |

---

## Алгоритм кражи работы

```python
queue: asyncio.Queue = asyncio.Queue()
for item in items:
    queue.put_nowait(item)

async def _worker(peer: PeerInfo) -> None:
    while True:
        batch = []
        for _ in range(batch_size):
            batch.append(queue.get_nowait())   # Выход при QueueEmpty
        if not batch:
            return
        results = await worker_fn(peer, batch)
        result_fn(results)

tasks = [asyncio.create_task(_worker(p)) for p in peers]
await asyncio.gather(*tasks)
```

**Особенности:**
- По одному воркеру на пир, запускаются через `asyncio.create_task()`
- Неблокирующее извлечение из общей очереди (`get_nowait()`) партиями `batch_size`
- Более быстрые пиры обрабатывают больше — естественная балансировка нагрузки

---

## DisableAwareStrategy (v4.67.0)

Дополнительная фильтрация по оверлею отключений:

```python
class DisableAwareStrategy(BatchInferenceStrategy):
    def select_peers(self, inference_type, peers, mode="parallel"):
        base = super().select_peers(inference_type, peers, mode)
        return [
            p for p in base
            if not self._state.is_disabled(p.peer_id, inference_type)
        ]
```

---

## Постоянство: data/mesh_inference_state.json

Оверлей отключений сохраняется атомарной записью:

```json
{
  "version": 1,
  "disabled": {
    "<peer_id>": ["tagger", "clip"]
  }
}
```

---

## Фасадный API

```python
from core.mesh_inference import get_router, has_mesh, set_router

router = get_router()
if router is not None:
    result = await router.dispatch_inference(
        inference_type="tagger",
        items=file_paths,
        batch_size=32,
        worker_fn=my_worker,
        result_fn=save_results,
        progress_fn=update_progress,
    )
```

| Функция | Описание |
|---------|---------|
| `get_router()` | Вернуть активный InferenceRouter (None если не зарегистрирован) |
| `has_mesh()` | Вернуть bool — доступен ли меш |
| `set_router(router)` | Вызывается CoworkManager при старте/остановке |
