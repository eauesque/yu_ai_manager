# 브라우저 호환성 보고서

**조사일:** 2026-02-23

## 지원 브라우저 (권장)

| 브라우저 | 최소 버전 | 전체 기능 버전 |
|----------|----------------|---------------------|
| Chrome   | 80+            | 94+                 |
| Firefox  | 74+            | 101+                |
| Safari   | 13.1+          | 16+                 |
| Edge     | 80+            | 94+                 |

IE11 및 이전 버전은 지원하지 않습니다.

---

## API 호환성

| 기능 | Chrome | Firefox | Safari | Edge | 비고 |
|---------|--------|---------|--------|------|-------|
| Fetch API / async/await | 55+ | 52+ | 11+ | 15+ | 모든 브라우저 지원 |
| AbortController | 66+ | 57+ | 11.1+ | 16+ | 모든 브라우저 지원 |
| IntersectionObserver | 51+ | 55+ | 12.1+ | 16+ | 무한 스크롤에 사용 |
| Optional chaining `?.` | 80+ | 74+ | 13.1+ | 80+ | 코드베이스 전반에서 광범위하게 사용 |
| scroll-snap | 69+ | 68+ | 13+ | 79+ | 독 카드에 사용 |
| `scrollbar-gutter` | 94+ | 101+ | **16+** | 94+ | Safari 15 이하 미지원 |
| `inset` CSS 약칭 | 102+ | 106+ | **16+** | 102+ | Safari 15 이하 미지원 |
| `backdrop-filter` | 76+ | **미지원** | 9+ | 79+ | Firefox 미지원 |
| `-webkit-backdrop-filter` | O | **미지원** | 9+ | O | Firefox 대안 없음 |

---

## 알려진 문제

### Firefox — `backdrop-filter` 미지원

- **영향 파일:** `dock-shell-panel.css`, `search-results-modal-nav.css`
- **증상:** 패널 블러 효과(글래스모피즘)가 렌더링되지 않아 배경이 투명하게 남음
- **심각도:** 시각적 품질 저하 (기능에는 영향 없음)
- **계획:** 미대응 (향후 Firefox용 불투명 배경 폴백 추가 가능)

### Safari 15 이하 — `scrollbar-gutter`, `inset` 미지원

- **영향 파일:** `dock-cards.css`, `uxpatch-i18n-paths.css`
- **증상:** 스크롤바 영역 떨림 및 미세한 위치 계산 오차
- **심각도:** 경미 (레이아웃 기능은 정상)

---

## 기존 호환성 조치 (모범 사례)

- `-webkit-backdrop-filter`와 표준 `backdrop-filter` 모두 선언
- Firefox 스크롤바는 `scrollbar-width` / `scrollbar-color` 사용
- WebKit 스크롤바는 `-webkit-scrollbar` 사용
- 파괴적 API (`crypto.randomUUID`, `structuredClone`, `.at()` 등) 미사용

---

## 향후 후보

| 항목 | 우선순위 | 설명 |
|------|----------|-------------|
| Firefox backdrop-filter 폴백 | P3 | 블러 없는 반투명 배경으로 전환 |
| `@supports` 조건부 쿼리 | P3 | CSS 기능 감지 |
