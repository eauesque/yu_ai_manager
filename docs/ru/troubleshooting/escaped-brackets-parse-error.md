# Баг исчезновения подсветки синтаксиса из-за экранированных скобок `\(` `\[` `\{`

**Версия**: Исправлено в v2.21.26
**Серьёзность**: P1 — влияет на все файлы с wildcard
**Дата обнаружения**: 2026-02-23

---

## Симптомы

При открытии файла wildcard в WC Manager (например, `__characters_genshin_impact__`)
подсветка синтаксиса работает только в первых строках — начиная со строки, содержащей `\(`,
все последующие строки теряют цветовую разметку.

Конкретно:
1. `(` в `\(` отображается как ERROR-токен красным
2. Все строки после этой теряют подсветку
3. LoRA-теги `<lora:...>` и веса `(tag:1.2)` тоже теряют цвет

---

## Первопричина

### Поток обработки на верхнем уровне (до исправления)

```
Вход: "yuko \(girls und panzer\), girls und panzer,"

1. i=0: 'y' → не совпадает ни с чем → вызов findTextEnd(text, 0)
2. findTextEnd: 'y','u','k','o',' ' → OK, '\' → OK (не в specials)
               '(' → в specials → break → возвращает j=6
3. TEXT токен: "yuko \" [0, 6)     ← '\' включён в текст
4. i=6: '(' → вызов matchParen(text, 6)
5. matchParen → findMatchingClose: depth=1, сканирование...
   - '\)' → воспринимается как escape, пропускается (j += 2)
   - Сканирование до конца файла без совпадающей ')'
   → return null
6. matchParen: result === null → ERROR токен { type: 'error', value: '(' }
7. Всё последующее рендерится некорректно
```

**Суть проблемы**: `findTextEnd` поглощает `\` как обычный текст,
затем `(` останавливает процесс, и `matchParen` запускается
для голой `(`, которую воспринимает как незакрытую скобку.

---

## Исправление

### Добавлена обработка экранированных скобок в `findTextEnd()`

**Файл**: `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-matchers-general.js`

```javascript
function findTextEnd(text, i) {
    const specials = ',\n|{}[]()<>_';
    let j = i;
    while (j < text.length) {
      // Экранированные скобки: \( \) \[ \] \{ \} → потреблять как буквальный текст
      if (text[j] === '\\' && j + 1 < text.length && '()[]{}'.includes(text[j + 1])) {
        j += 2;
        continue;
      }
      if (specials.includes(text[j])) break;
    }
    return j;
}
```

### Поток после исправления

```
Вход: "yuko \(girls und panzer\), girls und panzer,"

1. i=0: вызов findTextEnd(text, 0)
2. findTextEnd: 'y','u','k','o',' ' → OK
               '\' + '(' → обнаружена экранированная скобка → j += 2
               'g','i','r','l','s',...'r' → OK
               '\' + ')' → экранированная скобка → j += 2
               ',' → specials → break
3. TEXT токен: "yuko \(girls und panzer\)" [0, 30) ← всё как один текст
4. i=30: ',' → токен COMMA
5. Дальнейший разбор нормальный
```

---

## Проверочные случаи

| Тест | Ожидаемый результат | Статус |
|------|--------------------|----|
| `lumine \(genshin impact\)` | Один TEXT-токен, нет ERROR | PASS |
| Строки с `\(` перед `(masterpiece:1.2)` | SD_WEIGHT распознан нормально | PASS |
| `\[brackets\]` и `\{braces\}` | TEXT-токен, нет ERROR | PASS |
| Обычный `(masterpiece:1.2)` | SD_WEIGHT работает нормально | PASS |
| Обычный `{emphasis}` | NAI_EMPHASIS работает нормально | PASS |
| Внутренний `\(` в `(artist:a \(b\):1.2)` | SD_WEIGHT работает нормально | PASS |

---

## Связанные файлы

- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-matchers-general.js` — место исправления
- `docs/development/development_docs/SD_NAI_PROMPT_SYNTAX_SPEC.md` — Секция 9, спецификация escape
