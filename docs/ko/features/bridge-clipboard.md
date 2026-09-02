# Bridge 클립보드 단축키

NAI Bridge / ComfyUI Bridge / SD WebUI Bridge 페이지에서 단축키를 누르면
클립보드의 텍스트를 프롬프트 필드로 즉시 전송할 수 있습니다. 다른 창에서
프롬프트를 복사한 후, 텍스트 영역을 클릭하지 않고도 붙여넣을 수 있습니다.

## 단축키

| OS | 키 |
|---|---|
| Windows / Linux | `Ctrl` + `Alt` + `V` |
| macOS | `⌘` + `⌥` + `V` |

브라우저 기본 붙여넣기(`Ctrl`+`V`)와 별개로 추가된 것이며, 기존 붙여넣기
동작을 방해하지 않습니다.

## 동작

1. 임의의 Bridge 페이지를 엽니다
2. 외부에서 텍스트를 복사(`Ctrl`+`C`)
3. Bridge 페이지에서 `Ctrl`+`Alt`+`V` 누르기
4. 붙여넣기 대상:
   - 텍스트 영역에 포커스가 있는 경우 → 해당 영역의 캐럿 위치에 삽입
   - 포커스가 없는 경우 → 긍정 프롬프트에 삽입(NAI: `#nabPrompt` / ComfyUI: `#cfbPrompt` / SD: `#sdwbPrompt`)
5. 성공 시 토스트 "클립보드 내용을 붙여넣었습니다" 표시

## 대상 필드

| Bridge | 삽입 대상 (우선순위) |
|---|---|
| NAI Bridge | `nabPrompt` → `nabNegative` |
| ComfyUI Bridge | `cfbPrompt` → `cfbNegative` → `cfbWorkflowJson` |
| SD WebUI Bridge | `sdwbPrompt` → `sdwbNegative` |

## 브라우저 권한

브라우저의 **Clipboard API**(`navigator.clipboard.readText()`)를 사용하므로,
처음 사용 시 브라우저에서 클립보드 읽기 권한을 요청할 수 있습니다. 거부하면
작동하지 않습니다.

Clipboard API를 사용할 수 없는 구형 브라우저에서는 토스트 "클립보드 API를
사용할 수 없습니다"를 표시하고 아무 동작도 하지 않습니다. 일반적인
`Ctrl`+`V` 붙여넣기는 계속 사용할 수 있습니다.

## 제한 사항

- 일부 브라우저는 HTTPS 또는 `localhost`에서만 `navigator.clipboard`를
  사용할 수 있습니다 (Chrome은 `localhost`에서 허용)
- 이미지나 서식 있는 텍스트는 지원하지 않음 — 순수 플레인 텍스트만
- `<textarea>` 이외의 요소(예: `contenteditable`)에는 포커스가 있어도
  붙여넣기하지 않음
