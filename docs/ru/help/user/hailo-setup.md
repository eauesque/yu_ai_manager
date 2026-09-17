# Настройка Hailo-10H

Руководство по настройке на стороне хоста для использования Raspberry Pi 5 + Hailo AI Hat+ (Hailo-10H NPU) с YU AI Manager. Поскольку часть, связанная с оборудованием и ОС, не может быть выполнена через PyPI, требуется ручная подготовка.

> **Целевая аудитория**: Только если вы хотите включить расширения Hailo (GenAI Chat / Semantic Search / YOLO Detect / Tagger / Whisper) на Raspberry Pi 5 (рекомендуется 8 ГБ) с оборудованием Hailo-10H. В окружениях без оборудования Hailo никаких операций на этой странице не требуется.

---

## 1. Предварительные требования

- Raspberry Pi 5 (настоятельно рекомендуется 8 ГБ; с 4 ГБ сложно одновременно загружать несколько моделей из-за ограничений CMA)
- Hailo AI Hat+ (Hailo-10H)
- Raspberry Pi OS Bookworm 64-bit (aarch64)
- Python 3.13.x (зафиксирован в `<3.14` через `requires-python` в `pyproject.toml`; `uv` автоматически выбирает версию 3.13)

---

## 2. Установка драйвера PCIe

Hailo-10H использует выделенный модуль ядра `hailo1x_pci` (переименован из старого `hailo_pci` начиная с HailoRT 5.3.0).

```bash
sudo apt update
sudo apt install hailo-all
sudo reboot
```

Проверка после перезагрузки:

```bash
lsmod | grep hailo1x
ls /dev/h1x-0
dmesg | grep -i hailo | tail -20
```

Ожидаемые результаты:

- `hailo1x_pci` загружен
- Существует узел устройства `/dev/h1x-0` (не старый `/dev/hailo0`)
- В `dmesg` присутствуют строки `Firmware loaded in NNNN ms` и `Device created at /dev/h1x-0`

> **Отсутствие `/dev/hailo0` не является проблемой.** Начиная с HailoRT 5.3.0, `/dev/h1x-0` является значением по умолчанию, и данное приложение распознаёт оба (`core/llm_router/hailo_detect.py`).

---

## 3. Установка HailoRT (на стороне системы)

Бинарный файл `hailortcli` и разделяемая библиотека `libhailort.so`. Они включены в пакет `hailo-all`, но если вам нужна последняя версия, загрузите `.deb` из Hailo Developer Zone и установите поверх существующей версии.

Проверка:

```bash
hailortcli fw-control identify
```

Ожидаемый вывод (ключевые моменты):

```
Device Architecture: HAILO10H
Firmware Version: 5.3.0 (release,app)
```

---

## 4. Подготовка Python wheel (`hailort-*.whl`)

Это часть, недоступная через PyPI. **Python wheel для Hailo под aarch64 также недоступен в Hailo Developer Zone, поэтому его необходимо собрать вручную.**

### 4.1 Сборка из исходного кода

```bash
cd ~
git clone --branch v5.3.0 https://github.com/hailo-ai/hailort.git
cd hailort
./build.sh -aarch64
# По завершении в дереве сборки создаётся hailort-5.3.0-cp313-cp313-linux_aarch64.whl
```

(Подробности процесса сборки и зависимости см. в официальном README Hailo.)

### 4.2 Размещение wheel в домашнем каталоге

Скопируйте собранный wheel в **любое из следующих мест**; приложение автоматически обнаружит его при запуске:

| Путь поиска (приоритет) | Назначение |
|---|---|
| Переменная окружения `$HAILORT_WHEEL` | Произвольный полный путь (наивысший приоритет) |
| `$HOME/share/` | **Рекомендуемое расположение** |
| `$HOME/hailort/` | Когда дерево сборки сохраняется на месте исходного кода |
| `$HOME/Downloads/` | Временное расположение после загрузки |
| `$HOME/` (напрямую) | Последний резерв |

Рекомендуемая процедура:

```bash
mkdir -p ~/share
cp ~/hailort/hailort-5.3.0-cp313-cp313-linux_aarch64.whl ~/share/
```

### 4.3 Механизм автоматической установки

При запуске `./start.sh` выполняется `scripts/install_hailo.py`:

1. Проверяет, успешен ли `import hailo_platform` в venv
2. Только при ошибке: ищет wheel, **совместимый с текущей версией Python (cp313) + архитектурой (aarch64)**, по путям поиска выше
3. Устанавливает найденный последний wheel с помощью `uv pip install`
4. Если wheel не найден или уже установлен: никаких действий (тихая операция)

Таким образом, ручной запуск `uv pip install` не требуется. Достаточно поместить wheel в домашний каталог и перезапустить `./start.sh`.

---

## 4.4 Размещение файлов модели HEF

Разместите файлы HEF (модели, скомпилированные для NPU), используемые расширениями, в `~/hailo_models/`.

| Файл | Назначение | Примерный размер |
|---|---|---:|
| `yolov8n.hef` | Обнаружение объектов YOLO | 7 МБ |
| `clip_vit_b_16_image_encoder.hef` | **Semantic Search (изображение CLIP)** | 76 МБ |
| `clip_vit_b_16_text_encoder.hef` | Semantic Search (текст CLIP, опционально) | 77 МБ |
| `Whisper-{Tiny,Base,Small}.hef` | Распознавание речи | 75–405 МБ |
| `Qwen3-1.7B-Instruct.hef` | LLM Chat | 2,9 ГБ |
| `Qwen3-VL-2B-Instruct.hef` | VLM (изображение+текст) | 3,2 ГБ |

Прямая загрузка без аутентификации из S3-бакета Hailo Model Zoo (формат URL):

```
https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/<model>.hef
```

Пример (кодировщик изображений CLIP):

```bash
mkdir -p ~/hailo_models
curl -L -o ~/hailo_models/clip_vit_b_16_image_encoder.hef \
  https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/clip_vit_b_16_image_encoder.hef
```

> **При отсутствии файлов HEF расширение отображается как `Недоступно`.** Например, если статус Semantic Search показывает `hailo-10h (CLIP HEF не размещён)`, это означает, что `clip_vit_b_16_image_encoder.hef` отсутствует в `~/hailo_models/`. Для облегчения разграничения проблем оборудования или среды выполнения Python ответ содержит причины на трёх уровнях: `runtime_ok` / `hardware_ok` / `hef_ok` (наведите курсор на текст статуса для отображения подробностей).

Также можно указать другой каталог с помощью переменной окружения `HAILO_HEF_DIR`.

---

## 5. Параметры ядра (CMA)

Модели GenAI от Hailo (LLM/VLM/Whisper) требуют CMA (Contiguous Memory Allocator) для DMA.

Добавьте в конец `/boot/firmware/cmdline.txt`:

```
cma=256M
```

> **На Pi 5 (8 ГБ) значения `cma=1G` или `cma=512M` дают сбой без уведомления.** Поскольку ядро по умолчанию применяет `numa=fake=8`, CMA должна умещаться в пределах одного узла NUMA (1 ГБ), и при значении выше `256M` `CmaTotal=0` (без паники). Подробнее: [`docs/ja/hailo/PI5_NUMA_CMA_CONSTRAINTS.md`](../../hailo/PI5_NUMA_CMA_CONSTRAINTS.md)

Проверка после перезагрузки:

```bash
grep CmaTotal /proc/meminfo
# CmaTotal:         262144 kB  ← 256 МБ означает успех
```

Если значение `0 kB`, проверьте значение и при необходимости уменьшите его.

---

## 6. Совместная работа с hailo-ollama (опционально)

Если вы запускаете `hailo-ollama` (версию Ollama с Hailo NPU) на том же устройстве:

- **HailoRT 5.3.0 и новее**: Запустите с `HAILO_OLLAMA_VDEVICE_GROUP_ID=YU_SHARED hailo-ollama` для совместного использования физического устройства со стороной yu_ai_manager (group_id `YU_SHARED`); планировщик HailoRT будет выполнять time-slicing по алгоритму ROUND_ROBIN
- **До 5.2.0**: group_id не принимается, поэтому перед запуском yu_ai_manager необходимо остановить `hailo-ollama` командой `systemctl stop hailo-ollama`

---

## 7. Проверка работоспособности

После запуска `./start.sh` конфигурация успешна, если в WebUI в разделе **Настройки → Расширения** включены следующие пункты:

- `builtin_hailo_genai` (Hailo Chat / LLM / VLM / Speech2Text)
- `builtin_hailo_semantic_search` (CLIP Semantic Search)
- `builtin_hailo_yolo_detect` (Обнаружение объектов YOLO)

Или непосредственно через CLI:

```bash
uv run python -c "
from hailo_platform import VDevice
v = VDevice()
print('VDevice OK')
v.release()
"
```

---

## 8. Устранение неполадок

### Все расширения Hailo отображают «не загружено»

→ Python wheel, вероятно, не установлен. Проверьте:

```bash
uv run python -c "import hailo_platform; print(hailo_platform.__file__)"
```

При `ModuleNotFoundError`: поместите wheel в домашний каталог и перезапустите `./start.sh` (§4.2).

### `hailortcli fw-control identify` завершается с ошибкой `HAILO_OPEN_FILE_FAILURE`

→ Проблема с драйвером или узлом устройства. Проверьте, загружен ли `hailo1x_pci` в `lsmod | grep hailo1x` и существует ли `ls /dev/h1x-0`. Если оба отсутствуют, повторите §2 и перезагрузитесь.

### `HAILO_OUT_OF_HOST_MEMORY` при загрузке LLM/VLM / Pi зависает

→ Недостаточно CMA. Проверьте с помощью `grep CmaTotal /proc/meminfo`, доступно ли 256 МБ (§5). Поскольку `VDevice.release()` не возвращает CMA, после многократного переключения между моделями может потребоваться перезапуск процесса.

### `HAILO_OUT_OF_PHYSICAL_DEVICES(74)`

→ Другой процесс занимает VDevice. Определите виновника с помощью `lsof /dev/h1x-0` (как правило, это `hailo-ollama` или предыдущий процесс, не завершённый корректно через Ctrl+C), выполните `kill` и перезапустите.

### Python обновлён до 3.14 и несовместим с wheel

→ В этом репозитории в `pyproject.toml` зафиксировано `requires-python = ">=3.13,<3.14"`. Первый `uv sync` после клонирования выбирает 3.13.x. Если вручную было задано `.python-version = 3.14`, верните прежнее значение.

---

## 9. Связанная документация

- [`docs/ja/hailo/README.md`](../../hailo/README.md) — Оглавление документации по разработке Hailo-10H
- [`docs/ja/hailo/HAILORT_5_3_0_MIGRATION.md`](../../hailo/HAILORT_5_3_0_MIGRATION.md) — Заметки по миграции HailoRT 5.2.0 → 5.3.0
- [`docs/ja/hailo/PI5_NUMA_CMA_CONSTRAINTS.md`](../../hailo/PI5_NUMA_CMA_CONSTRAINTS.md) — Подробности об ограничениях CMA Pi 5
- [`scripts/install_hailo.py`](../../../../scripts/install_hailo.py) — Скрипт автоматического обнаружения wheel
