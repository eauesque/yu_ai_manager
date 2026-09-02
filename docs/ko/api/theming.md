# 테마 — CSS Custom Properties

레퍼런스 UI (`ui/default/`)에서 사용되는 CSS 커스텀 프로퍼티 목록입니다.
커스텀 UI에서 이 변수들을 재정의하여 기존 컴포넌트의 외관을 변경할 수 있습니다.

소스: `ui/default/static/css/base/base-theme.css`

## 핵심 변수 (`:root` / `body.dark`)

| 변수 | 라이트 | 다크 | 용도 |
|----------|-------|------|---------|
| `--bg` | `#f5f6f8` | `#0f1115` | 페이지 배경 |
| `--card` | `#ffffff` | `#1b1f2a` | 카드/패널 배경 |
| `--text` | `#222` | `#e7eaf0` | 기본 텍스트 |
| `--muted` | `#666` | `#aab2c0` | 보조 텍스트/힌트 |
| `--border` | `#e6e6e6` | `#2b3240` | 테두리/구분선 |
| `--shadow` | `0 4px 14px rgba(0,0,0,0.08)` | `0 10px 26px rgba(0,0,0,0.45)` | 카드 그림자 |
| `--btn-bg` | `#ffffff` | `#1b2030` | 버튼 배경 |
| `--btn-text` | `#222` | `#e7eaf0` | 버튼 텍스트 |
| `--btn-hover` | `#f6f9ff` | `#222a3d` | 버튼 호버 |
| `--tooltip-bg` | `rgba(0,0,0,0.85)` | `rgba(0,0,0,0.92)` | 툴팁 배경 |
| `--tooltip-text` | `#fff` | `#fff` | 툴팁 텍스트 |
| `--accent` | `#2563eb` | `#60a5fa` | 강조 색상 (링크, 버튼 하이라이트) |

## 다크 모드 변수

### 태그 토큰

| 변수 | 값 | 용도 |
|----------|-------|---------|
| `--tag-bg` | `#4a4a4a` | 태그 배경 |
| `--tag-text` | `#f0f0f0` | 태그 텍스트 |
| `--tag-border` | `#666` | 태그 테두리 |
| `--tag-hover-bg` | `#5a5a5a` | 태그 호버 배경 |
| `--tag-hover-border` | `#888` | 태그 호버 테두리 |
| `--tag-focus-ring` | `#60a5fa` | 태그 포커스 링 |

### 태그 카테고리 변형

| 변수 | 용도 |
|----------|---------|
| `--tag-ns-*` | 네임스페이스 태그 (bg, border, text) |
| `--tag-wh-*` | 높은 가중치 태그 |
| `--tag-wl-*` | 낮은 가중치 태그 |
| `--tag-we-*` | 강조 가중치 태그 |

### 네거티브 프롬프트

| 변수 | 값 | 용도 |
|----------|-------|---------|
| `--neg-prompt-bg` | `#2d2424` | 네거티브 프롬프트 배경 |
| `--neg-prompt-border` | `#fc8181` | 네거티브 프롬프트 테두리 |
| `--neg-heading` | `#fc8181` | 네거티브 헤딩 |

### 아코디언

| 변수 | 값 | 용도 |
|----------|-------|---------|
| `--accordion-bg` | `#252525` | 아코디언 배경 |
| `--accordion-border` | `#3a3a3a` | 아코디언 테두리 |
| `--accordion-header-bg` | `#2a2a2a` | 헤더 배경 |
| `--accordion-header-text` | `#e0e0e0` | 헤더 텍스트 |

## 테마 클래스

| 클래스 | 설명 |
|-------|-------------|
| `body.dark` | 다크 모드 |
| `body.theme-retro` | 레트로 네온 테마 (코나미 코드) |
| `body.theme-glow` | 커스텀 글로우 이펙트 |

## 테마 적용

커스텀 UI에서 테마를 변경하려면:

```css
/* 커스텀 테마 예시 */
body.theme-ocean {
  --bg: #0a1628;
  --card: #132744;
  --text: #c8daf0;
  --accent: #38bdf8;
  color-scheme: dark;
}
```

`body` 요소에 클래스를 추가하면 테마가 적용됩니다.
다크 모드에서 `color-scheme: dark` 속성은 OS 폼 컨트롤 색상에 영향을 줍니다.
