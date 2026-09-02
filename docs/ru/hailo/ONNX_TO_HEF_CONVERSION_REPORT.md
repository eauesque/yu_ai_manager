# Отчёт о конвертации ONNX в HEF

**Дата проведения**: 2026-03-06
**Цель**: Конвертация ONNX-моделей WD-Tagger в формат Hailo HEF для инференса на Raspberry Pi 5 + AI HAT 2 (Hailo-10H)
**Результат**: Неудача (конвертация невозможна для всех вариантов моделей)

---

## Окружение

| Параметр | Описание |
|----------|----------|
| ОС | Ubuntu 24.04 (WSL2) |
| Python | 3.11.13 (установлен через uv) |
| Hailo Dataflow Compiler | v5.2.0 |
| GPU | CUDA 12.8, Driver 591 |
| RAM | 151GB |

---

## Испытанные модели

### 1. wd-swinv2-tagger-v3 (SwinTransformer V2)

- **Источник**: `SmilingWolf/wd-swinv2-tagger-v3` (446MB)
- **Вход**: `[batch, 448, 448, 3]` float32
- **Выход**: `[batch, 10861]` float32
- **Результат**: Неудача
- **Ошибка**: `IndexError: list index out of range` в `_convert_axes_to_nhwc`
- **Причина**: Преобразование осей LayerNormalization не поддерживается в DFC v5.2.0

### 2. wd-vit-tagger-v3 (Vision Transformer)

- **Источник**: `SmilingWolf/wd-vit-tagger-v3` (362MB)
- **Вход**: `[batch, 448, 448, 3]` float32
- **Выход**: `[batch, 10861]` float32
- **Результат**: Неудача
- **Ошибка**: То же (`IndexError` в `_convert_axes_to_nhwc`)
- **Причина**: ViT тоже использует LayerNormalization, сбой в том же месте

### 3. wd-convnext-tagger-v3 (ConvNeXt)

- **Источник**: `SmilingWolf/wd-convnext-tagger-v3` (377MB)
- **Вход**: `[batch, 448, 448, 3]` float32
- **Выход**: `[batch, 10861]` float32
- **Результат**: Неудача
- **Ошибка**: `UnsupportedShuffleLayerError` (множество узлов Transpose) + `UnsupportedModelError` (несоответствие shape в Mul)
- **Причина**: Операции Transpose, характерные для channels-last дизайна ConvNeXt, не поддерживаются DFC

---

## Первопричина сбоев

ONNX-парсер DFC v5.2.0 не может корректно обработать следующие операции:

1. **LayerNormalization**: Ошибка индекса при преобразовании осей NHWC для LayerNorm над тензорами размерности 3+
2. **Transpose (Shuffle)**: Паттерны Transpose для конвертации channels-last/first в ConvNeXt не поддерживаются

Все варианты WD-Tagger (SwinV2, ViT, ConvNeXt) используют LayerNormalization — современную архитектуру, которую DFC v5.2.0 не может сконвертировать.

---

## Калибровочные данные

- Случайно выбрано 500 изображений из вывода ComfyUI / Stable Diffusion forge
- Применена та же предобработка, что и в WD-Tagger (RGBA→RGB белый фон, масштабирование с сохранением пропорций, белые поля, BGR)
- Сохранено как `calibration_data.npy`, но не использовано (конвертация не дошла до этого шага)

---

## Возможные перспективы

- **Будущие версии DFC**: При улучшении поддержки LayerNormalization / Transpose в Hailo повторная попытка будет оправдана
- **Модификация модели**: Создание модифицированной версии с заменой LayerNorm на BatchNorm (большие трудозатраты, риск деградации точности)
- **Сохранение текущего подхода**: Продолжить инференс через ONNX Runtime (CPU)
