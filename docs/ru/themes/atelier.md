# Система Atelier (γ)

**Atelier System** — это визуальная идентичность, введённая в yu_ai_manager — гибридный язык дизайна Editorial × Refined × Brutalist.

## Иерархия бренда

**eauesque** (брэнд продукта) > **yu_ai_manager** (приложение) > **Atelier System** (название системы дизайна)

Atelier System находится на том же уровне, что и Material / Fluent, организованная под брэндом продукта eauesque.

## Модель внедрения: дополнительная тема на основе опт-ин

Существующие темы (light / dark / theme-retro / theme-glow) остаются без изменений. Atelier применяется **добавлением** `body.theme-atelier-light` или `body.theme-atelier-dark` — без деструктивного замещения.

- **Новые пользователи**: по умолчанию Atelier light / dark (следует `prefers-color-scheme` системы)
- **Возвращающиеся пользователи**: настройки сохранены; вы можете вернуться на legacy в любой момент

Переключение через Параметры → Разное → "Atelier Theme".

## Гибрид трёх шрифтов

| Роль | Шрифт | Примечания |
|---|---|---|
| Display + body | **Fraunces** Variable | оси opsz/wght управляют h1=96 / h2=48 / h3=24 / body=14 / eyebrow=11 с соответствием оптического размера |
| UI sans | **Inter** Variable | Навигация, кнопки, ярлыки, eyebrow |
| Data mono | **JetBrains Mono** Variable | Синтаксис подсказки (веса, LoRA, embeddings), значения метаданных |

Все размещены локально (подмножество Latin Extended). Fraunces 176K / Inter 148K / JetBrains Mono 52K. Лицензия SIL Open Font v1.1.

Регенерировать через `scripts/build_atelier_fonts.py`.

## Двухуровневые акценты

| Токен | Назначение | Light / Dark |
|---|---|---|
| `--accent-warm` | Декоративный, атмосфера, избранное | `#c9a063` / `#d4a96e` |
| `--accent-tool` | Действие, контур фокуса, активное состояние | `#2f5c8a` / `#5a8fc5` |

Разделение декорации и действия делает UI-affordances однозначными с первого взгляда.

## --canvas (нейтрально-серая область изображения)

Регионы изображений AI (область изображения модального окна, сетка миниатюр) находятся на **нейтрально-сером холсте**, отделённом от тёплого UI-хрома, чтобы восприятие цвета изображения не было предвзятым:

- `--canvas`: `#d4d4d2` (light) / `#1a1a1a` (dark)
- `--canvas-raised`: `#c8c8c6` (light) / `#222222` (dark)

Chrome (`--bg`, `--surface`, `--surface-raised`) сохраняет семейство тёплый-бежевый.

## Проверка контраста WCAG

8 пар × light/dark = 16 случаев, подтверждено `tests/test_atelier_wcag.py`. Текст тела 4.5:1, побочный (контур фокуса / eyebrow) 3:1.

```
uv run pytest tests/test_atelier_wcag.py
```

## Модальное окно

- Область изображения: `--canvas`
- Информационная панель: `--surface-raised` + Fraunces roman (без курсива)
- Тело подсказки: Fraunces roman; `(...:1.2)` и `<lora:...>` переходят на встроенный JetBrains Mono
- Панель инструментов (v4.126.2 круговые таблетки): glass + accent-tool активен
- Закрыть / стрелка навигации / кнопка избранного: glass + контур фокуса accent-tool
- Избранное активно: тёплый акцент (декоративный, отделён от синего инструмента)

## Логотип заголовка

Двухстрочное построение:
- Строка 1: `yu` (Fraunces 22pt)
- Строка 2: `eauesque` (подпись JetBrains Mono 9pt)

Редакционная подпись, которая визуализирует иерархию бренда. Legacy nav-brand остаётся на месте для не-atelier тем.

## Файлы

```
ui/default/static/css/atelier/
  atelier-tokens.css       # @font-face + body.theme-atelier-* + tokens
  atelier-components.css   # h1-h3, p, eyebrow, glass btn, prompt-syntax
  atelier-index.css        # logo + sidebar + grid + pill search
  atelier-modal.css        # full modal (canvas + glass + accent-tool)

ui/default/static/fonts/atelier/
  Fraunces-VariableFont.subset.woff2     # 176K
  Inter-VariableFont.subset.woff2        # 148K
  JetBrainsMono-VariableFont.subset.woff2 # 52K
  LICENSE.md                              # OFL v1.1
```

## Доступность

- `prefers-reduced-motion: reduce` отменяет transform/animation (переходы непрозрачности сохранены)
- `:focus-visible` везде использует `--accent-tool` контур 2px + смещение 2px (WCAG 2.5.5 + 1.4.11)
- WCAG AA (4.5:1 тело, 3:1 побочный) проверено на 16 парах

## Путь отката

Если что-то пошло не так, Параметры → "Atelier Theme" → "Off" мгновенно восстанавливает legacy light/dark. Пользовательские темы (preset-*) не затрагиваются.
