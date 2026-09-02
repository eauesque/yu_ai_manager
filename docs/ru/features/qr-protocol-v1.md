# YU QR Protocol v1 — унифицированная спецификация нагрузки

**Версия:** 1.0
**Дата:** 2026-02-23
**Целевое приложение:** YU AI Manager (TagDB)

---

## Обзор

YU AI Manager поддерживает совместное использование приглашений и диагностику ошибок через QR коды.
Этот документ предоставляет унифицированную спецификацию для формата нагрузки QR кода.

### Используемые библиотеки

| Назначение | Библиотека | Версия |
|------|-----------|-----------|
| Генерирование QR | QRCode.js | 1.0.0 |
| Чтение QR | jsQR | 1.4.0 |

### Ограничения ёмкости QR

- Максимум символов: **2,953** (уровень исправления ошибок M)
- Выше 2,500 символов: мета JSON минифицирован и повторён попытку
- Выше 2,953 символов: ошибка (`qr.info.too_long`)

---

## Тип нагрузки 1 — совместное использование приглашения

### Происхождение

- `GET /api/share/<file_id>` -> Python `build_share_data_payload()`
- `routes/share_ops/payload_build.py`

### JSON схема

```json
{
  "v":   "1.0",
  "t":   "prompt",
  "p":   "<positive prompt>",
  "n":   "<negative prompt>",
  "src": "TagDB",
  "m":   "<model name>",
  "s":   "<seed>",
  "st":  "<steps>",
  "cfg": "<CFG scale>",
  "sa":  "<sampler>",
  "sz":  "<WxH>"
}
```

### Определения полей

| Ключ | Тип | Требуется | Описание | Ограничение |
|------|-----|------|------|------|
| `v` | string | ✅ | Версия протокола. В настоящее время `"1.0"` | — |
| `t` | string | ✅ | Тип нагрузки. В настоящее время всегда `"prompt"` | — |
| `p` | string | ✅ | Позитивное приглашение | 2,000 символов |
| `n` | string | ✅ | Отрицательное приглашение | 1,000 символов |
| `src` | string | ✅ | Идентификатор издателя. В настоящее время всегда `"TagDB"` | — |
| `m` | string | — | Имя модели | — |
| `s` | string | — | Значение начального числа | — |
| `st` | string | — | Количество шагов | — |
| `cfg` | string | — | CFG масштаб | — |
| `sa` | string | — | Имя семплера | — |
| `sz` | string | — | Размер изображения в формате `"WxH"` | — |

---

## QR режимы — 4 типа

### Режим `positive`

```
qrText = shareData.p
```

- Содержание: Только текст позитивного приглашения
- Вариант использования: Прямое совместное использование текста приглашений

### Режим `negative`

```
qrText = shareData.n
```

- Содержание: Только текст отрицательного приглашения

### Режим `meta`

```
qrText = JSON.stringify(shareData, null, 0)
```

- Содержание: Вся нагрузка JSON совместного использования приглашений, уплотнённая
- Возвращается к красивомупечатному `JSON.stringify` когда результат превышает 2,500 символов

### Режим `url`

```
encoded = btoa(unescape(encodeURIComponent(JSON.stringify(shareData))))
qrText  = "{origin}/share?data={encoded}"
```

- Содержание: URL к странице совместного использования YU AI Manager
- Отключена на localhost (`localhost` / `127.0.0.1`)

---

## Тип нагрузки 2 — диагностика ошибок

### Происхождение

- Генерируется при HTTP ошибках -> `_render_error_page()`
- `core/web/app_factory_handlers.py`

### JSON схема

```json
{
  "s": "<HTTP status code>",
  "p": "<request path>",
  "v": "<APP_VERSION>"
}
```

### Определения полей

| Ключ | Тип | Описание | Ограничение |
|------|-----|------|------|
| `s` | string | Код статуса HTTP (`"404"`, `"500"` и т.д.) | — |
| `p` | string | Путь запроса | 80 символов |
| `v` | string | Версия приложения (из файла `APP_VERSION`) | — |

---

## Процедура декодирования URL совместного использования

Декодирование на странице совместного использования (`/share?data=...`):

```javascript
const encoded = new URL(location).searchParams.get('data');
const json    = decodeURIComponent(escape(atob(encoded)));
const data    = JSON.parse(json);
```

---

## Параметры генерирования QR

```javascript
new QRCode(container, {
  text:         qrText,
  width:        200,   // 180 на страницах ошибок
  height:       200,   // 180 на страницах ошибок
  colorDark:    '#000000',
  colorLight:   '#ffffff',
  correctLevel: QRCode.CorrectLevel.M,  // 15% исправление ошибок
});
```

---

## Будущие расширения (v1.x)

| Функция | Статус | Примечания |
|------|------|------|
| Экспорт QR коллекции (несколько изображений) | Не реализовано | Запланировано как тип нагрузки 3 |
| Тип `t: "collection"` | Не определено | Список ID файлов + имя коллекции |
| Сжатие (gzip + Base64) | Не реализовано | Альтернатива для приглашений превышающих 2,953 символов |

---

## Файлы реализации

| Файл | Роль |
|----------|------|
| `routes/share.py` | Share API Blueprint |
| `routes/share_ops/payload_build.py` | Генерирование нагрузки |
| `routes/share_ops/prompt_extract.py` | Извлечение данных приглашения |
| `core/web/app_factory_handlers.py` | Генерирование данных QR ошибки |
| `static/js/runtime/tools/runtime-tools-qr-core.js` | Построение и отображение QR |
| `static/js/runtime/tools/runtime-tools-qr.js` | Обработчики QR UI |
| `static/js/share/share-qr.js` | Декодирование изображения QR |
| `static/js/share/share-page.js` | Отображение страницы совместного использования |
| `static/vendor/qrcode.min.js` | Библиотека QRCode.js |
| `static/vendor/jsQR.min.js` | Библиотека jsQR |
