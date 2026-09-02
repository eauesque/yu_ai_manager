# Atelier System (γ)

yu_ai_manager 프런트엔드에 도입된 **Atelier System** 은 에디토리얼 × 정제 × 브루탈리스트 하이브리드의 visual identity 디자인 시스템입니다.

## 브랜드 계층

**eauesque** (제품 브랜드) > **yu_ai_manager** (앱) > **Atelier System** (디자인 시스템 명칭)

Atelier System 은 Material / Fluent 와 동급의 디자인 시스템으로, eauesque 제품 브랜드 하위에 자리합니다.

## 도입 방식: opt-in 추가 테마

기존 light / dark / theme-retro / theme-glow 테마는 영향받지 않습니다. Atelier 는 `body.theme-atelier-light` / `body.theme-atelier-dark` 클래스를 **추가** 하여 적용되는 opt-in 방식입니다.

- **신규 사용자**: 기본값으로 Atelier light / dark (시스템 `prefers-color-scheme` 따름)
- **기존 사용자**: 설정 보존 (퇴각 경로 확보, 언제든 legacy 로 복귀 가능)

전환: 설정 → Misc → "Atelier 테마"。

## 3 서체 하이브리드

| 역할 | 서체 | 비고 |
|---|---|---|
| display + body | **Fraunces** Variable | opsz/wght 축으로 h1=96 / h2=48 / h3=24 / body=14 / eyebrow=11 광학 크기 매칭 |
| UI sans | **Inter** Variable | 내비게이션, 버튼, 라벨, eyebrow |
| data mono | **JetBrains Mono** Variable | prompt 구문 (가중치・LoRA・embed), 메타데이터 값 |

모두 self-hosted (Latin Extended 서브셋). Fraunces 176K / Inter 148K / JetBrains Mono 52K. SIL Open Font License v1.1.

`scripts/build_atelier_fonts.py` 로 재생성 가능.

## 이중 accent

| 토큰 | 용도 | 값 (light / dark) |
|---|---|---|
| `--accent-warm` | 장식, 분위기, 즐겨찾기 | `#c9a063` / `#d4a96e` |
| `--accent-tool` | 액션, focus outline, active 상태 | `#2f5c8a` / `#5a8fc5` |

의미 분리로 "장식"과 "조작"이 한눈에 구분됩니다.

## --canvas (이미지 영역 전용 neutral grey)

AI 생성 이미지의 색상 지각을 왜곡하지 않도록, 이미지 표시 영역 (modal 이미지 영역, 썸네일 그리드) 은 warm chrome 과 분리된 **중립 회색** 토큰을 사용합니다:

- `--canvas`: `#d4d4d2` (light) / `#1a1a1a` (dark)
- `--canvas-raised`: `#c8c8c6` (light) / `#222222` (dark)

UI chrome (`--bg`, `--surface`, `--surface-raised`) 은 warm-tan 계열 유지.

## WCAG 대비 검증

8 쌍 × light/dark = 16 케이스를 `tests/test_atelier_wcag.py` 가 자동 검증. 본문 4.5:1, 부수 (focus outline・eyebrow) 3:1 보장.

```
uv run pytest tests/test_atelier_wcag.py
```

## Modal 설계

- 이미지 영역: `--canvas`
- 정보 패널: `--surface-raised` + Fraunces roman (이탤릭 미사용)
- prompt 본문: Fraunces roman; syntax `(...:1.2)` `<lora:...>` 는 inline JetBrains Mono
- toolbar (v4.126.2 원형 pill): glass + accent-tool active
- close / nav arrow / fav-btn: glass + accent-tool focus outline
- 즐겨찾기 active: warm accent (장식적, tool blue 와 분리)

## Header Logo

2 단 구성:
- 1 단: `yu` (Fraunces 22pt)
- 2 단: `eauesque` (JetBrains Mono 9pt 시그니처)

브랜드 계층을 시각화하는 editorial signature. 비 atelier 테마는 기존 nav-brand 유지.

## 파일 구성

```
ui/default/static/css/atelier/
  atelier-tokens.css       # @font-face + body.theme-atelier-* + tokens
  atelier-components.css   # h1-h3, p, eyebrow, glass btn, prompt-syntax
  atelier-index.css        # logo + sidebar + grid + pill 검색
  atelier-modal.css        # 전체 modal (canvas + glass + accent-tool)

ui/default/static/fonts/atelier/
  Fraunces-VariableFont.subset.woff2     # 176K
  Inter-VariableFont.subset.woff2        # 148K
  JetBrainsMono-VariableFont.subset.woff2 # 52K
  LICENSE.md                              # OFL v1.1
```

## 접근성

- `prefers-reduced-motion: reduce` 로 transform/animation 억제 (opacity 전환은 유지)
- `:focus-visible` 은 전부 `--accent-tool` 2px outline + 2px offset (WCAG 2.5.5 + 1.4.11)
- WCAG AA (본문 4.5:1, 부수 3:1) 16 쌍 검증 완료

## 퇴각 경로

문제 발생 시 설정 → "Atelier 테마" → "끄기" 로 즉시 legacy light/dark 로 복귀. 커스텀 테마 (preset-*) 영향 없음.
