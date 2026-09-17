# 이스케이프된 괄호 `\(` `\[` `\{`로 인한 구문 색상 손실

**버전**: v2.21.26에서 수정됨
**심각도**: P1 -- 모든 와일드카드 파일에 영향
**발견일**: 2026-02-23

---

## 증상

WC Manager가 와일드카드 파일(예: `__characters_genshin_impact__`)에서 `\(`를 만나면 구문 색상이 사라집니다. 파일의 처음 몇 줄은 올바른 색상으로 렌더링되지만, `\(`를 포함하는 항목 이후의 모든 줄에서 하이라이팅이 완전히 사라집니다.

구체적으로:
1. `\(`의 `(`가 빨간색 ERROR 토큰으로 렌더링됩니다.
2. 이후의 모든 항목에서 구문 하이라이팅이 완전히 사라집니다.
3. LoRA 태그 `<lora:...>`와 가중치 `(tag:1.2)`도 색상을 잃습니다.

### 영향을 받는 데이터 예시

```
lumine \(genshin impact\)
yuko \(girls und panzer\), girls und panzer,
(artist:example_artist \(art style\):1.2)
```

- 1번 줄: `\(`가 ERROR를 발생시킵니다. `genshin impact\)` 이후의 모든 것이 잘못된 토큰이 됩니다.
- 2번 줄 이후: 이전 줄의 `matchParen`이 나머지 텍스트를 스캔하여 과대한 토큰에 흡수시켜 모든 색상을 파괴합니다.
- 3번 줄은 `\(`가 `()` 안에 있을 때 올바르게 작동합니다. `findMatchingClose`가 이스케이프를 올바르게 처리하기 때문입니다. 이 비대칭성이 혼란의 원인이었습니다.

---

## 근본 원인

### 최상위 토크나이저 흐름 (수정 전)

```
입력: "yuko \(girls und panzer\), girls und panzer,"

1. i=0: 'y' → 일치하는 매처 없음 → findTextEnd(text, 0)
2. findTextEnd: 'y','u','k','o',' ' → OK, '\' → OK (specials에 없음)
                '(' → specials에 있음 → break → j=6 반환
3. TEXT 토큰: "yuko \" [0, 6)     ← '\'가 텍스트로 소비됨
4. i=6: '(' → matchParen(text, 6)
5. matchParen → findMatchingClose(text, 6, '(', ')')
6. findMatchingClose: depth=1, 내부 스캔:
   - 'g','i','r','l','s'... → OK
   - '\)' → 이스케이프로 건너뜀 (j += 2)  ← '\)'가 닫는 괄호로 인식되지 않음!
   - ',' ' ' 'g','i','r','l','s'... → 후속 줄까지 스캔
   - EOF에 도달하지만 매칭 ')'를 찾지 못함
   → null 반환
7. matchParen: result === null → ERROR 토큰 { type: 'error', value: '(' }
8. i=7: 나머지 텍스트가 조각으로 파싱됨. 연속이어야 할 토큰들이
   분리되어 후속 줄의 모든 하이라이팅이 파괴됨
```

**핵심 문제**: `findTextEnd`가 `\`를 일반 텍스트로 소비한 후 뒤따르는 `(`에서 멈춥니다. 단독 `(`가 메인 루프의 `text[i] === '('` 체크에 도달하여 `matchParen`을 발동시킵니다. `findMatchingClose` 내부에서 `\)`가 이스케이프로 건너뛰어져 닫는 괄호로 인식되지 않습니다. 매칭 검색이 EOF까지 진행됩니다.

### 괄호 내부와 최상위 수준의 비대칭성

`findMatchingClose`에는 이미 이스케이프 처리가 있습니다:
```javascript
if (text[j] === '\\' && j + 1 < text.length) { j += 2; continue; }
```

이것은 `(artist:example_artist \(art style\):1.2)`와 같이 **괄호 내부**의 이스케이프에서는 올바르게 작동합니다. 외부 `()`가 먼저 매칭되고, 내부 `\(` `\)` 쌍은 건너뛰어집니다.

그러나 **최상위 수준**에서는 `\`와 `(`가 별도의 단계에서 처리되어 하나의 이스케이프 시퀀스로 인식되지 않습니다. 이것이 버그의 근본 원인입니다.

---

## 수정

### `findTextEnd()`에 이스케이프 괄호 처리 추가

**파일**: `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-matchers-general.js`

```javascript
function findTextEnd(text, i) {
    const specials = ',\n|{}[]()<>_';
    let j = i;
    while (j < text.length) {
      // 이스케이프된 괄호: \( \) \[ \] \{ \} → 리터럴 텍스트로 소비
      if (text[j] === '\\' && j + 1 < text.length && '()[]{}'.includes(text[j + 1])) {
        j += 2;
        continue;
      }
      if (specials.includes(text[j])) break;
      // ... 기존 체크 ...
    }
    return j;
}
```

### 수정 후 흐름

```
입력: "yuko \(girls und panzer\), girls und panzer,"

1. i=0: findTextEnd(text, 0)
2. findTextEnd: 'y','u','k','o',' ' → OK
                '\' + '(' → 이스케이프된 괄호 감지 → j += 2 (둘 다 소비)
                'g','i','r','l','s',' ','u','n','d',' ','p','a','n','z','e','r' → OK
                '\' + ')' → 이스케이프된 괄호 감지 → j += 2
                ')' 이미 소비됨 → ',' → specials → break
3. TEXT 토큰: "yuko \(girls und panzer\)" [0, 30)  ← 전체 범위가 하나의 토큰
4. i=30: ',' → COMMA 토큰
5. 파싱이 정상적으로 계속됨
```

### 변경 범위

- 6개의 이스케이프 시퀀스(`\(`, `\)`, `\[`, `\]`, `\{`, `\}`) 모두 최상위 수준에서 텍스트로 소비됩니다.
- 괄호 표현식 내부의 이스케이프 처리(`findMatchingClose` / `findMatchingBrace`)는 변경되지 않았습니다.
- `()`, `[]`, `{}`의 일반 괄호 매칭은 영향을 받지 않습니다.
- 이 수정은 프롬프트 구문 사양 섹션 9에 정의된 이스케이프 표기를 준수합니다.

---

## 검증

| 테스트 | 예상 결과 | 상태 |
|--------|----------|------|
| `lumine \(genshin impact\)` | 단일 TEXT 토큰, ERROR 없음 | PASS |
| 여러 `\(` 줄 다음의 `(masterpiece:1.2)` | SD_WEIGHT로 인식됨 | PASS |
| `\[brackets\]`와 `\{braces\}` | TEXT 토큰, ERROR 없음 | PASS |
| 일반 `(masterpiece:1.2)` | SD_WEIGHT로 작동 | PASS |
| 일반 `{emphasis}` | NAI_EMPHASIS로 작동 | PASS |
| 일반 `[suppress]` | NAI_SUPPRESS로 작동 | PASS |
| 괄호 안의 `\(`: `(artist:a \(b\):1.2)` | SD_WEIGHT로 작동 | PASS |
| 평문 재구성 | 입력과 일치 | PASS |

---

## 관련 파일

- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-matchers-general.js` -- 수정 위치
- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-main.js` -- 토크나이저 메인 루프
- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-helpers.js` -- `findMatchingClose`
- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-matchers-paren.js` -- `matchParen`
- `docs/development/development_docs/SD_NAI_PROMPT_SYNTAX_SPEC.md` -- 섹션 9 이스케이프 사양
