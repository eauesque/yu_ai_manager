# Материалы по разработке Hailo-10H AI Hat+

Записи о реализации AI-инференса на Raspberry Pi 5 + Hailo AI Hat+ (Hailo-10H).

Публикуем знания, накопленные в ходе реальной разработки в областях,
где официальная документация недостаточна.

## Список документов

| Файл | Содержание |
|------|-----------|
| [HAILORT_5_3_0_MIGRATION.md](HAILORT_5_3_0_MIGRATION.md) | Заметки по миграции с HailoRT 5.2.0 на 5.3.0. Различия API, переименование узла устройства (`/dev/h1x-0`), совместимость HEF, скрипт smoke-теста |
| [VDEVICE_SHARING_PATTERN.md](VDEVICE_SHARING_PATTERN.md) | Паттерн реализации общего менеджера VDevice для совместной работы нескольких моделей (YOLO/CLIP/LLM/VLM/Whisper) в одном процессе |
| [PI5_NUMA_CMA_CONSTRAINTS.md](PI5_NUMA_CMA_CONSTRAINTS.md) | Ограничения выделения CMA на Pi 5 (поведение при `numa=fake=8`). Почему `cma=1G` тихо проваливается, подтверждённый предел и рекомендуемое значение `cma-512` (`dtoverlay=cma,cma-512` в `config.txt`), требования Hailo GenAI к памяти, поведение без возврата CMA при `VDevice.release()` |
| [HAILO_SEMANTIC_SEARCH_DEVLOG.md](HAILO_SEMANTIC_SEARCH_DEVLOG.md) | Дневник разработки семантического поиска CLIP. Записи реализации по фазам, проблемы и их решения |
| [HAILO_DEVICE_CONTROL.md](HAILO_DEVICE_CONTROL.md) | Управление устройством Hailo, управление VDevice, эксклюзивный доступ, переключение моделей |
| [ONNX_TO_HEF_CONVERSION_GUIDE.md](ONNX_TO_HEF_CONVERSION_GUIDE.md) | Инструкция по конвертации ONNX → HEF. Dataflow Compiler, квантование, устранение неполадок |
| [ONNX_TO_HEF_CONVERSION_REPORT.md](ONNX_TO_HEF_CONVERSION_REPORT.md) | Отчёт о валидации конвертации (DFC v5.2.0). Подробный анализ сбоев для трёх вариантов WD-Tagger |
| [WD_TAGGER_DFC_5_3_0_FOLLOWUP.md](WD_TAGGER_DFC_5_3_0_FOLLOWUP.md) | Продолжение про DFC v5.3.0. Повторная проверка тех же трёх моделей WD-Tagger 3 (по-прежнему сбой), а также выявленные улучшения v5.3.0 (новый `_create_layer_normalization_layer`, поток повтора через onnxsim, рекомендация end-node) |
| [CLIP_ONNX_DEVLOG.md](CLIP_ONNX_DEVLOG.md) | Дневник разработки CLIP ONNX мультибэкенда. Запасной вариант для окружений без Hailo |
| [HAILO_CMA_LEAK_HAILORT_5_3_0.md](HAILO_CMA_LEAK_HAILORT_5_3_0.md) | **Структурные ограничения и измерения утечки CMA**. То, что `VDevice.release()` не возвращает память, непрерывная утечка во время инференса (около 14 МБ/мин), а также то, что **память не возвращается ни при завершении дочернего процесса, ни при выходе процесса, ни при выгрузке модуля** (измерено дважды независимо в Phase 0 PoC, при SIGTERM + ожидании 30 секунд возвращается лишь +8 МБ). Единственный надёжный способ восстановления — перезагрузка самого Pi **(старый вывод. Исправлен по итогам повторного тестирования на HailoRT / driver 5.4.0 в §8 документа [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md))** |
| [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) | **Исправление и повторная проверка вышеуказанного диагноза утечки CMA**. A/B-сравнение официальной vanilla-версии и версии с патчем `FOLL_LONGTERM` на HailoRT / driver 5.4.0 показало, что прежний диагноз был ошибочным, основанным лишь на абсолютном значении восстановления `CmaFree` после первой загрузки HEF. Приведены различия исходного кода v5.3.0 → v5.4.0, подводные камни самостоятельной сборки и данные измерений |
| [HAILO_AUTO_REBOOT_PHASE05.md](HAILO_AUTO_REBOOT_PHASE05.md) | Руководство по эксплуатации маршрута автоматической перезагрузки, принятого по итогам вышеуказанного. Фаза наблюдения (только запись `would_fire` без перезагрузки), пороги принятия решения, причина значения по умолчанию `mode = "off"` |
| [HAILO_AUTO_REBOOT_PHASE05_RUNBOOK.md](HAILO_AUTO_REBOOT_PHASE05_RUNBOOK.md) | Runbook той же фазы для данного окружения. Порядок запуска, проверки и завершения наблюдения |
| [HAILO_LLM_SUBPROCESS_DEVLOG.md](HAILO_LLM_SUBPROCESS_DEVLOG.md) | Лог реализации, устранивший зависание event loop Quart из-за GIL во время cold_load (~71 сек) путём изоляции LLM chat-инференса в отдельном subprocess |
| [HAILO_10H_ECOSYSTEM_ASSESSMENT.md](HAILO_10H_ECOSYSTEM_ASSESSMENT.md) | Оценка экосистемы Hailo-10H (по состоянию на 2026-03-19, HailoRT/DFC v5.2.0) |

## Важные известные факты

### Окружение / Raspberry Pi 5

- **Максимум CMA на Pi 5 (8 ГБ) — 512 МБ, настраивается в `config.txt`**: Ядро по умолчанию применяет `numa=fake=8`, разбивая RAM на 8 узлов NUMA по 1 ГБ. CMA должна умещаться в границы одного узла, поэтому `cma-1024` и `cma-768` тихо проваливаются (`CmaTotal=0` без паники ядра). **`cma-512` — подтверждённый предел и рекомендуемое значение** (повторно проверено 2026-05-16 через overlay, `CmaTotal: 524288 kB`). Из-за регрессии firmware в 2026-05 следует использовать не cmdline `cma=`, а `dtoverlay=cma,cma-512` в `/boot/firmware/config.txt`. Подробности в [PI5_NUMA_CMA_CONSTRAINTS.md](PI5_NUMA_CMA_CONSTRAINTS.md)
- **После каждой перезагрузки обязательно проверять CMA**: `grep CmaTotal /proc/meminfo`. Если 0 — настройка игнорирована
- **`VDevice.release()` не возвращает CMA**: CMA удерживается в течение всей сессии ОС. Воспринимайте VDevice как синглтон в рамках сессии. **Не восстанавливается даже при перезапуске процесса** — то, что память не возвращается ни при завершении дочернего процесса, ни при выходе процесса, ни при выгрузке модуля, дважды независимо подтверждено измерениями в Phase 0 PoC (при SIGTERM + ожидании 30 секунд возвращается лишь +8 МБ при ожидаемых ≥250 МБ). Единственный надёжный способ восстановления — `sudo reboot` самого Pi (power-cycle PCIe). Подробности и принятое решение см. в [HAILO_CMA_LEAK_HAILORT_5_3_0.md](HAILO_CMA_LEAK_HAILORT_5_3_0.md). **Исправление**: данный пункт основан на старых измерениях. Повторное A/B-тестирование на HailoRT / driver 5.4.0 не выявило практической утечки CMA; исправлено в §8 документа [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md)
- **`numa=fake=8` влияет на установку Node.js**: Память NUMA-узла (1 ГБ) ошибочно воспринимается как общий RAM, из-за чего установщики npm/node прерываются. Сообщено в апстрим: [anthropics/claude-code#33864](https://github.com/anthropics/claude-code/issues/33864)
- **Python wheel требует сборки из исходников**: На PyPI и в Hailo Developer Zone нет wheel для aarch64
- **Взаимное исключение с hailo-ollama**: Во время использования VDevice нужно останавливать hailo-ollama
- **Утечка VDevice при завершении процесса**: Проверяйте через `lsof /dev/hailo*` и завершайте `kill PID`

### VDevice / API

- **Использовать InferModel API**: `VDevice.create_infer_model()` — правильный вариант. Старый VStreams API (`InferVStreams`, `ConfigureParams.create_from_hef`) возвращает `HAILO_NOT_IMPLEMENTED` на Hailo-10H
- **InferModel поддерживает только простые модели**: Hailo HEF с 1 входом (YOLO) работает, но для HEF Whisper с 2 входами и 4 выходами `configure()` возвращает `HAILO_INVALID_ARGUMENT`. Для сложных моделей используйте GenAI SDK
- **VDevice отображается на один физический девайс**: Создание двух экземпляров `VDevice()` одновременно даёт `HAILO_OUT_OF_PHYSICAL_DEVICES(74)`
- **При смене модели полностью освобождать VDevice**: Простой сброс ссылки Python в `None` недостаточен. Явно вызывайте `VDevice.release()` перед созданием нового VDevice
- **`set_format_type(FormatType.FLOAT32)` не поддерживается в hailort 5.2.0**: Атрибут `format_type` отсутствует. Выполняйте квантование/деквантование uint8 вручную или используйте GenAI SDK
- **Выход квантован в uint8**: Выделение буфера для вывода как float32 даёт `buffer size mismatch`. Выделяйте как uint8, затем конвертируйте в float32 с параметрами деквантования (scale, zero_point)

### GenAI (LLM / VLM / Speech2Text)

- **В HailoRT 5.3.0 `temperature=0.0` отклоняется**: `LLM.generate()` с `temperature=0` выбрасывает `HAILO_INVALID_ARGUMENT`. Перед вызовом зажимайте: `temperature = max(temperature, 0.01)`. Влияет, когда OpenAI-совместимые клиенты по умолчанию шлют `temperature=0`
- **Одновременная загрузка двух GenAI-моделей возможна**: LLM + Whisper-tiny можно загрузить одновременно на один VDevice (проверено на HailoRT 5.3.0). CMA при обеих загрузках: ~10 МБ из 256 МБ. Whisper-base и крупнее скорее всего переполнят память
- **Бюджет CMA для LLM + Whisper-tiny**: ~246 МБ суммарно (измеренное значение). Числа CMA для всех моделей в [PI5_NUMA_CMA_CONSTRAINTS.md](PI5_NUMA_CMA_CONSTRAINTS.md)

### Whisper (распознавание речи)

- **Использовать GenAI SDK**: `hailo_platform.genai.Speech2Text` обеспечивает полный пайплайн. Энкодер + декодер полностью выполняются на NPU
- **HEF только для декодера**: `Whisper-Base.hef` имеет 2 входа (encoder_features + token_embeddings) и 4 выхода (vocab, разбитый на 4 части). С InferModel API не работает
- **Вход GenAI SDK**: PCM-аудиоданные в формате little-endian float32 (`<f4`), нормализованные к [-1,1]
- **Запасной вариант ONNX**: Если GenAI SDK недоступен, энкодер + декодер выполняются на CPU через ONNX-модель с HuggingFace

### YOLO (обнаружение объектов)

- **Работает с InferModel API**: HEF с 1 входом без проблем
- **Запасной вариант ONNX**: При недоступности Hailo автоматически скачивается `yolo11n.onnx`. Выход `(1,84,8400)` совместим с yolov8n
- **Охлаждение при сбое инициализации**: 60 секунд без повторных попыток после сбоя инициализации

### Распределённый инференс

- **Проверка работоспособности обязательна**: Проверяйте доступность удалённых узлов через `filter_available()` перед началом распределения
- **При сбое удалённого узла**: Возврат оставшихся элементов на локальную обработку. Повторное обнаружение при восстановлении со следующего батча
- **Распределение нагрузки**: Разница в скорости GPU и NPU значительна, равномерное разбиение неэффективно. Динамическое распределение на основе измерения пропускной способности — задача на будущее
