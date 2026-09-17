# Danbooru автоматическое теггирование — спецификация реализации

**Статус**: Реализовано (Phase 1-5: v2.77.0)
**Цель**: YU AI Manager
**Назначение**: Автоматически назначать теги Danbooru изображениям AI с использованием двухуровневого подхода: WD-Tagger ONNX (CPU) + VLM (OpenAI-compatible API)
**Реализация**: `extensions/builtin_wd_tagger/core_impl/` (12 файлов), `routes/wd_tagger.py` (11 API)

---

## Статус реализации

| Фаза | Статус | Расположение |
|---|---|---|
| Фаза 1: WD-Tagger ONNX | **Завершено** | `extensions/builtin_wd_tagger/core_impl/engine_onnx.py` |
| Фаза 2: VLM Engine (OpenAI-compatible) | **Завершено** (v2.77.0) | `extensions/builtin_wd_tagger/core_impl/engine_vlm.py` + `engine_composite.py` |
| Фаза 3: Постобработка тегов | **Завершено** (v2.77.0) | `extensions/builtin_wd_tagger/core_impl/tag_postprocess.py` |
| Фаза 4: Batch API | **Завершено** | `extensions/builtin_wd_tagger/core_impl/batch_ops.py` + `routes/wd_tagger.py` |
| Фаза 5: UI | **Завершено** | Страница инструментов + модальное окно деталей с WD значками + просмотр XMP |

### Обзор реализации фаза 2/3 (v2.77.0-v2.77.1)

- **VLM Engine** (`engine_vlm.py`): Автоматический резервный вариант между OpenAI-compatible API и Ollama native API
- **Composite Engine** (`engine_composite.py`): Двухуровневый конвейер ONNX + VLM (Режим B)
- **Постобработка тегов** (`tag_postprocess.py`): Нормализация (нижний регистр, подчёркивание, удаление недопустимых символов, дедупликация) + фильтр NSFW (~30 тегов)
- **Engine Factory**: Маршрутизация по `engine_type` ("onnx" / "vlm" / "both")
- **UI**: Выбор типа движка, URL/модель/параметры тайм-аута VLM, тест соединения, фильтр NSFW
- **API**: `GET /api/wd-tagger/vlm/test`, `GET /api/wd-tagger/vlm/models`
- **MCP**: инструменты `wd_tagger_vlm_test`, `wd_tagger_vlm_models`
- **Протестировано**: Реальное теггирование изображения подтверждено с Ollama qwen2.5vl:7b, 23 модульных теста успешно

---

## Предшествующее искусство

### DeepDanbooru (KichangKim)
- **Подход**: Модель классификации изображений (TensorFlow) для прямого предсказания тегов
- **Сильные стороны**: Быстро, специализировано на тегах, конвертируемо в ONNX
- **Слабые стороны**: Фиксированный набор тегов, невозможно адаптироваться к новым тегам
- **Ссылка**: Уже интегрировано в A1111

### WD-Tagger (SmilingWolf) — Принято в фазе 1
- **Подход**: Преемник DeepDanbooru. Четыре архитектуры: SwinV2/ViT/ConvNeXt/EVA02
- **Сильные стороны**: Выше точность чем DeepDanbooru, включена классификация категорий (general/character/copyright/rating)
- **ONNX**: Официальные модели ONNX + `selected_tags.csv` распределены на HuggingFace
- **Input**: 448x448 RGB (соотношение сторон сохранено + белое заполнение)

### DanTagGen / DTG (KohakuBlueleaf)
- **Подход**: LLaMA-based LLM (400M) для генерации тегов и их дополнения
- **Сильные стороны**: Контекстная дополнение тегов
- **Слабые стороны**: Медленно из-за LLM умозаключений
- **HuggingFace**: `KBlueLeaf/DanTagGen-beta`

### Обоснование проектирования
Система поддерживает **как** WD-Tagger ONNX (быстро, надёжно), так и Qwen2-VL через hailo-ollama (гибко, контекстно-осведомлено), поэтому пользователи могут выбрать правильный инструмент для работы.

---

## Архитектура

```
[Вход изображения]
    |
[Выбор движка]  (engine_factory.py)
    |-- WD-Tagger ONNX (быстро, фиксированный набор тегов ~10,000 тегов)  [Фаза 1: реализовано]
    |       | Оценки уверенности + категоризированный список тегов
    |-- Qwen2-VL через hailo-ollama (медленно, гибко, контекстно-осведомлено)   [Фаза 2]
    |       | JSON массив -> парсинг тегов
    |-- Двухуровневый: ONNX -> дополнение Qwen2-VL                    [Опция фазы 2]
    |       | Передать теги ONNX в промпт, дать LLM генерировать дополнительные теги
    |
[Постобработка: нормализация тегов, фильтр NSFW]  [Фаза 3]
    |
[БД: сохранить в таблицу file_wd_tags]  (store.py)
[XMP: встроить в файл (опционально)]  (xmp_write.py)
```

---

## Фаза 1: WD-Tagger ONNX Engine — Реализовано

**Модель**: SmilingWolf/wd-swinv2-tagger-v3 (рекомендуется), ViT v3, ConvNeXt v3, EVA02-Large v3

**Файлы реализации** (`extensions/builtin_wd_tagger/core_impl/`):
| Файл | Строки | Роль |
|---|---|---|
| `types.py` | ~60 | TagPrediction, WdTagResult, WdTaggerEngine ABC |
| `tag_csv.py` | ~70 | Парсинг selected_tags.csv, отображение категорий |
| `model_download.py` | ~120 | Загрузка с HuggingFace HTTP |
| `engine_onnx.py` | ~150 | ONNX умозаключение (448x448, BGR, пороговая фильтрация) |
| `engine_factory.py` | ~50 | Кэш движка + создание |
| `store.py` | ~130 | DB CRUD (таблица file_wd_tags) |
| `xmp_xml.py` | ~60 | Конструкция XMP пакета |
| `xmp_read.py` | ~90 | Чтение XMP |
| `xmp_write.py` | ~160 | Запись XMP в PNG/JPEG/WebP |
| `config_ops.py` | ~70 | config.json чтение/запись |
| `single_ops.py` | ~80 | Конвейер теггирования одного изображения |
| `batch_ops.py` | ~120 | Пакетная обработка (интеграция JobManager) |

**БД**: таблица `file_wd_tags` (схема v14)
```sql
CREATE TABLE file_wd_tags (
    id         INTEGER PRIMARY KEY,
    file_id    INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    tag_name   TEXT NOT NULL,
    confidence REAL NOT NULL,
    category   TEXT NOT NULL DEFAULT 'general',
    model      TEXT NOT NULL,
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    UNIQUE(file_id, tag_name, model)
);
```

**API**: `routes/wd_tagger.py` — 11 конечных точек

---

## Фаза 2: VLM Engine (OpenAI-compatible API) — Реализовано (v2.77.0)

**Назначение**: Дополнить WD-Tagger ONNX подробными описаниями и контекстными тегами, которые ONNX не может захватить
**Реализация**: `extensions/builtin_wd_tagger/core_impl/engine_vlm.py` (универсальный OpenAI-compatible VLM движок)
**Примечание**: Исходная спецификация планировала Hailo-специфичный `engine_hailo.py`, но фактическая реализация использует универсальный движок `engine_vlm.py`, который обрабатывает Ollama, hailo-ollama и другие OpenAI-compatible серверы одинаково. Поддерживает автоматический резервный вариант между OpenAI-compatible API (`/v1/chat/completions`) и Ollama native API (`/api/chat`).

### Конфигурация оборудования

| Элемент | Спецификация |
|---|---|
| **Device** | Raspberry Pi 5 + Hailo-10H AI ускоритель |
| **Memory** | 8GB RAM |
| **VLM Model** | **Qwen2-VL-2B-Instruct** (единственный VLM в Hailo Model Zoo) |
| **Inference Framework** | hailo-ollama (OpenAI-compatible API) |
| **Endpoint** | `http://<pi-ip>:8000/v1/chat/completions` |

### Характеристики модели

- **Qwen2-VL-2B-Instruct**: Модель Vision-Language из семейства Qwen (2B параметров)
- Принадлежит к семейству Qwen, не к семейству llava. Точность понимания изображений обычно выше чем у моделей на основе llava
- При 2B параметров удобно вписывается в Hailo-10H 8GB RAM
- Текстовый Qwen2 (1.5B) подтверждён работающим с hailo-ollama
- **Примечание**: По состоянию на 2026-02, это единственный VLM доступный для Hailo-10H

### Дизайн промпта

```python
SYSTEM_PROMPT = """You are a Danbooru image tagging assistant.
Analyze the image and output ONLY Danbooru-style tags as a JSON array.
Rules:
- Use underscores instead of spaces (e.g., long_hair, blue_eyes)
- Output ONLY the JSON array, no other text
- Include tags for: character count, gender, hair, eyes, clothing, pose, background, art style
- Do NOT include copyright or character name tags unless clearly identifiable
- Maximum 40 tags
Example output: ["1girl", "solo", "long_hair", "blue_eyes", "smile"]"""

USER_PROMPT = "Tag this image with Danbooru tags."
```

### Дизайн реализации (`extensions/builtin_wd_tagger/core_impl/engine_hailo.py` — ~100 строк)

```python
import base64
import json
import logging
import urllib.request
from pathlib import Path

from .types import TagPrediction, WdTagResult, WdTaggerEngine

logger = logging.getLogger(__name__)

_USER_AGENT = "YU-AI-Manager/2.0 (WD-Tagger Qwen2-VL)"

class HailoQwen2VLEngine(WdTaggerEngine):
    """Qwen2-VL-2B-Instruct через hailo-ollama (OpenAI-compatible API)."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        model: str = "qwen2-vl:2b",
        timeout: int = 60,
    ):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def tag_image(self, image_path: str) -> WdTagResult:
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode()

        # Умозаключение MIME типа
        suffix = Path(image_path).suffix.lower()
        mime = {"png": "image/png", "webp": "image/webp"}.get(
            suffix.lstrip("."), "image/jpeg"
        )

        payload = json.dumps({
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {
                            "url": f"data:{mime};base64,{image_b64}"
                        }},
                        {"type": "text", "text": USER_PROMPT},
                    ],
                },
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 512,
            "temperature": 0.3,
        }).encode()

        req = urllib.request.Request(
            f"{self._base_url}/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": _USER_AGENT,
            },
        )

        resp = urllib.request.urlopen(req, timeout=self._timeout)
        data = json.loads(resp.read())
        content = data["choices"][0]["message"]["content"]
        raw_tags = json.loads(content)

        # Формат ответа: список или {"tags": [...]}
        if isinstance(raw_tags, dict) and "tags" in raw_tags:
            raw_tags = raw_tags["tags"]
        if not isinstance(raw_tags, list):
            raw_tags = []

        tags = []
        for t in raw_tags:
            name = str(t).strip().lower().replace(" ", "_")
            if name:
                tags.append(TagPrediction(
                    tag=name,
                    confidence=0.5,  # LLMs не возвращают оценки уверенности
                    category="general",
                ))

        return WdTagResult(tags=tags, model=self._model)

    def get_name(self) -> str:
        return f"Qwen2-VL ({self._model})"

    def is_available(self) -> bool:
        """Проверка подключения к серверу hailo-ollama."""
        try:
            req = urllib.request.Request(
                f"{self._base_url}/v1/models",
                headers={"User-Agent": _USER_AGENT},
            )
            resp = urllib.request.urlopen(req, timeout=5)
            return resp.status == 200
        except Exception:
            return False
```

### Режимы работы

**Режим A: Qwen2-VL самостоятельно**
```
Изображение -> Qwen2-VL -> JSON массив тегов -> Нормализация -> Сохранение в БД
```
- LLM напрямую анализирует изображение и генерирует теги
- Нет оценок уверенности (равномерно установлены на 0.5)
- Гибкое теггирование без фиксированного набора тегов
- Скорость: ~3-10 секунд на изображение (оценка на Hailo-10H)

**Режим B: WD-Tagger ONNX -> дополнение Qwen2-VL (двухуровневый)**
```
Изображение -> WD-Tagger ONNX -> Теги с высокой уверенностью (>=0.7)
                              |
                              v
    Qwen2-VL: "Эти теги описывают изображение. Предложите дополнительные теги."
                              |
                              v
    Теги ONNX + теги дополнения LLM -> Слияние -> Нормализация -> Сохранение в БД
```
- Сочетает надёжные теги ONNX с контекстным пониманием LLM
- Включение тегов ONNX в промпт должно улучшить точность LLM
- Скорость: ONNX (~0.5s) + LLM (~3-10s) = ~4-11 секунд на изображение

**Промпт режима B**:
```python
補完_SYSTEM_PROMPT = """You are a Danbooru image tagging assistant.
The image already has these tags from automated classification: {existing_tags}
Analyze the image and suggest ADDITIONAL Danbooru-style tags not in the list above.
Output ONLY a JSON array of new tags. Use underscores instead of spaces.
Focus on: composition, mood, background details, specific clothing items, art style.
Maximum 20 additional tags.
Example: ["looking_at_viewer", "outdoors", "cloudy_sky", "pleated_skirt"]"""
```

### Дополнение к engine_factory.py

```python
# Дополнение к get_engine() в engine_factory.py

engine_type = config.get("engine_type", "onnx")  # "onnx" | "hailo" | "both"

if engine_type == "hailo":
    from .engine_hailo import HailoQwen2VLEngine
    engine = HailoQwen2VLEngine(
        base_url=config.get("hailo_url", "http://localhost:8000"),
        model=config.get("hailo_model", "qwen2-vl:2b"),
        timeout=config.get("hailo_timeout", 60),
    )
elif engine_type == "both":
    # Двухуровневый: ONNX -> дополнение Hailo (опция фазы 2)
    ...
```

### Записи config.json

```json
{
  "wd_tagger": {
    "model": "SmilingWolf/wd-swinv2-tagger-v3",
    "general_threshold": 0.35,
    "character_threshold": 0.85,
    "write_xmp": true,
    "auto_download": true,
    "engine_type": "onnx",
    "hailo_url": "http://localhost:8000",
    "hailo_model": "qwen2-vl:2b",
    "hailo_timeout": 60
  }
}
```

### Проверка перед реализацией (тестирование оборудования Pi)

1. **Подтверждение того, что Qwen2-VL-2B-Instruct запускается на hailo-ollama**
   ```bash
   # На Pi
   hailo-ollama run qwen2-vl:2b
   ```

2. **Подтверждение того, что запросы vision работают через OpenAI-compatible API**
   ```bash
   curl -X POST http://localhost:8000/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "qwen2-vl:2b",
       "messages": [{"role": "user", "content": [
         {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/..."}},
         {"type": "text", "text": "What is in this image?"}
       ]}],
       "max_tokens": 256
     }'
   ```

3. **Подтверждение того, что вывод Danbooru-format JSON стабилен**
   - Проверка поддержки `response_format: json_object` в hailo-ollama
   - Требуется резервный вариант с извлечением JSON на основе регулярных выражений из текстового вывода, если не поддерживается

4. **Измерение фактической скорости умозаключения** — секунды на изображение (требуется для вычисления размера пакета)

---

## Фаза 3: Постобработка тегов — Реализовано (v2.77.0)

**Реализация**: `extensions/builtin_wd_tagger/core_impl/tag_postprocess.py`
**Интеграция**: Автоматически применена после умозаключения в `single_ops.py` / `batch_ops.py`

```python
class TagPostProcessor:
    INVALID_CHARS = set('[](){}"\'/\\')
    MAX_TAG_LEN = 100

    def normalize(self, tags: list[str]) -> list[str]:
        result = []
        for tag in tags:
            tag = tag.strip().lower()
            tag = tag.replace(" ", "_")
            # Удалить недопустимые символы
            tag = "".join(c for c in tag if c not in self.INVALID_CHARS)
            if 1 <= len(tag) <= self.MAX_TAG_LEN:
                result.append(tag)
        # Дедупликация и сортировка
        return sorted(set(result))

    def filter_nsfw(self, tags: list[str], allow_nsfw: bool) -> list[str]:
        # Список тегов NSFW (управляется в отдельном файле)
        if allow_nsfw:
            return tags
        return [t for t in tags if t not in NSFW_TAG_SET]
```

**Интеграция с фазой 1**:
- WD-Tagger ONNX уже разделяет теги рейтинга, используя категорию 9 (rating)
- Фильтр NSFW использует теги рейтинга (`explicit`, `questionable`) плюс дополнительный список NSFW
- Реализация: `extensions/builtin_wd_tagger/core_impl/tag_postprocess.py` (~80 строк)

---

## Фаза 4: Batch Processing API — Реализовано

**API** (`routes/wd_tagger.py`):

| Метод | Путь | Назначение |
|---|---|---|
| POST | `/api/wd-tagger/batch` | Запустить пакет (file_ids, limit, force) |
| POST | `/api/wd-tagger/tag/<file_id>` | Теггировать одно изображение |
| GET | `/api/wd-tagger/tags/<file_id>` | Получить теги |
| DELETE | `/api/wd-tagger/tags/<file_id>` | Удалить теги |
| GET | `/api/wd-tagger/stats` | Статистика |
| GET | `/api/wd-tagger/untagged` | Список незакодированных файлов |
| GET/POST | `/api/wd-tagger/config` | CRUD параметров |
| POST | `/api/wd-tagger/model/download` | Загрузка модели |
| GET | `/api/wd-tagger/model/status` | Статус модели |
| GET | `/api/wd-tagger/xmp/<file_id>` | Чтение XMP |

**Поток обработки** (`batch_ops.py`):
1. Обработка файлов в `file_ids` последовательно (по умолчанию незакодированные файлы с `meta_source=unknown` когда не указано)
2. Запустить умозаключение через движок
3. UPSERT в таблицу `file_wd_tags` (движок определён столбцом model)
4. Встроить XMP в файл (опционально)
5. Отслеживать прогресс и поддерживать отмену через JobManager

---

## Фаза 5: UI — Реализовано

**Страница инструментов** (`templates/tools/content/primary/_wd_tagger.html`):
- Выбор модели (4 модели), ползунки порогов (general/character)
- Переключатель записи XMP, кнопка загрузки модели
- Кнопка выполнения пакета + полоса прогресса
- Отображение статистики (количество тегов, распределение по категориям, количество незакодированных)

**Модальное окно деталей**:
- Значки тегов WD (general=синий, character=зелёный, copyright=оранжевый, rating=красный)
- Кнопка просмотра XMP (dc:subject + wdtag namespace + сырой XML)
- Щелчок по тегу запускает поиск

---

## Структура файла (текущая)

```
extensions/builtin_wd_tagger/core_impl/
├── __init__.py              # Инициализация модуля
├── types.py                 # TagPrediction, WdTagResult, WdTaggerEngine ABC
├── tag_csv.py               # Парсинг selected_tags.csv
├── model_download.py        # Загрузка модели с HuggingFace
├── engine_onnx.py           # Умозаключение WD-Tagger ONNX [Фаза 1]
├── engine_vlm.py            # VLM движок (OpenAI-compatible) [Фаза 2: завершено]
├── engine_composite.py      # ONNX + VLM двухуровневый [Фаза 2: завершено]
├── engine_factory.py        # Создание движка + кэш
├── store.py                 # DB CRUD (file_wd_tags)
├── xmp_xml.py               # Конструкция XMP пакета
├── xmp_read.py              # Чтение XMP
├── xmp_write.py             # Запись XMP (PNG/JPEG/WebP)
├── config_ops.py            # config.json чтение/запись
├── single_ops.py            # Конвейер теггирования одного изображения
├── batch_ops.py             # Пакетная обработка (JobManager)
├── batch_processors.py      # Внутренняя логика пакетной обработки
└── tag_postprocess.py       # Нормализация тегов, фильтр NSFW [Фаза 3: завершено]

routes/wd_tagger.py          # API конечные точки (11 всего)

src/ts/tools-page/wd-tagger/
├── core.ts                  # CRUD параметров, пакет, загрузка модели
└── render.ts                # Отображение DOM

src/ts/runtime-tools-ui/tools/
└── wd-tags.ts               # Модальное окно деталей WD теги + просмотр XMP
```

---

## Приоритет реализации (обновлено)

```
Фаза 1 (WD-Tagger ONNX)        -> Завершено
Фаза 4 (Batch API)              -> Завершено
Фаза 5 (UI)                     -> Завершено
Фаза 3 (Постобработка/NSFW)   -> Далее (~80 дополнительных строк)
Фаза 2 (Qwen2-VL hailo-ollama) -> После тестирования оборудования Pi (~100 дополнительных строк + изменения factory)
```

---

## Ссылки

- WD-Tagger (SmilingWolf): https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3
- DeepDanbooru: https://github.com/KichangKim/DeepDanbooru
- DanTagGen: https://huggingface.co/KBlueLeaf/DanTagGen-beta
- Hailo Model Zoo VLM: Qwen2-VL-2B-Instruct (hailo.ai Model Explorer)
- hailo-ollama API спецификация: Обратитесь к источнику модифицированного форка

---

*Создано: 2026-02-27 / Обновлено: 2026-02-27 (реализация фазы 1 завершена, фаза 2 пересмотрена на основе Qwen2-VL)*
