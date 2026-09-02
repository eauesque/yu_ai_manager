# API Sweeps

Конечные точки для истории выполнения sweep Bridge (оси параметров NAI / SD WebUI / ComfyUI).

Информация о выполнении сохраняется в таблицах `sweeps` / `sweep_axes` (миграция 68) начиная с версии 4.183.0. Список истории страницы `/sweep/<id>` отображается через этот API.

## GET /api/sweeps/history

Возвращает недавние sweeps. Используется `/sweep/<id>` для отображения фильтров "те же условия, что и текущий sweep".

### Параметры запроса

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `limit` | int (1..500) | 50 | Максимальное количество возвращаемых записей |
| `ref` | string | — | ID справочного sweep; требуется, если установлен `match` |
| `match` | CSV | — | Список полей, разделённых запятыми, для сравнения со справкой |
| `tol_steps` | string | `exact` | Допуск для шагов: `exact` / `5` / `10` / `20` (процент) |
| `tol_cfg` | string | `exact` | Допуск для CFG (одинаковые значения) |
| `completed_only` | `0`/`1` | `0` | `1` сохраняет только `status='completed'` |
| `saved_only` | `0`/`1` | `0` | `1` сохраняет только строки с ненулевым `first_file_id` |
| `axis_count` | string | `all` | `all` / `1` / `2` / `3` |
| `date_range` | string | `all` | `all` / `today` / `week` / `month` |

#### Допустимые ключи `match`

- `bridge` / `checkpoint` / `vae` / `sampler` — равенство строк
- `positive` / `negative` — равенство `prompt_template` / `negative_template`
- `axisX` / `axisY` / `axisZ` — `sweep_axes.param` при axis_index 0/1/2 должен совпадать
- `resolution` — совпадение `width` И `height`
- `steps` / `cfg` — числовое совпадение (`tol_*` контролирует допуск)
- `baseSeed` — совпадение `base_seed`

Ключи, для которых справочный sweep не имеет значения, молча игнорируются (в пользовательском интерфейсе соответствующий флажок отключён).

### Ответ

```json
{
  "ok": true,
  "data": {
    "entries": [
      {
        "id": "uuid-xxxx",
        "bridge": "nai",
        "base_seed": 1234567,
        "created_at": 1714992000,
        "prompt_template": "best quality, ...",
        "negative_template": "worst quality, ...",
        "checkpoint": "nai-anime-v3",
        "vae": null,
        "sampler": "k_euler",
        "width": 832,
        "height": 1216,
        "steps": 28,
        "cfg": 5.5,
        "axis_count": 1,
        "first_file_id": 12345,
        "last_file_id": 12399,
        "file_count": 6,
        "status": "completed",
        "updated_at": 1714992100,
        "axes_params": ["cfg_rescale"]
      }
    ],
    "total": 142
  }
}
```

`total` — это количество нефильтрованных строк `sweeps`, используется для значка "{shown} / {total} match".

## GET /api/sweep/info/<file_id>

Читает пакет XMP из `file_id` и возвращает структурированные метаданные sweep. Смотрите `core/bridge_core/sweep_xmp.py`.

## GET /api/sweep/files/<sweep_id>

Сканирует родительскую папку файла подсказки `file_id` и возвращает каждый файл, чей XMP содержит тот же ID sweep.

## Как заполняются строки

- **При сохранении**: `core/bridge_core/bridge_save_batch.py` вызывает `upsert_sweep_from_meta()` после автоимпорта. Заголовок выполнения и оси записываются с первого взгляда; последующие батчи обновляют только `last_file_id` / `file_count` / `updated_at`.
- **Обратное заполнение для старых файлов**: `uv run python scripts/backfill_sweeps.py [--db PATH] [--limit N]`. Проходит файлы `has_sweep=1` и восстанавливает строки из атрибутов XMP. Идемпотентно.

## Известные ограничения

- Асинхронный путь сохранения (`return_file_ids=False`) может оставить `first_file_id` NULL. Пользовательский интерфейс затем отображает строку как нечитаемый элемент.
- `prompt_template` / `negative_template` сохраняются один раз за запуск. Подстановки стиля S/R по оси не восстанавливаются; значения осей по изображению остаются в пакете XMP и читаются `/api/sweep/info/<file_id>`.
