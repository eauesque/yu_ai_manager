# 瀏覽器相容性報告

**調查日期：** 2026-02-23

## 支援的瀏覽器（建議）

| 瀏覽器 | 最低版本 | 完整功能版本 |
|----------|----------------|---------------------|
| Chrome   | 80+            | 94+                 |
| Firefox  | 74+            | 101+                |
| Safari   | 13.1+          | 16+                 |
| Edge     | 80+            | 94+                 |

不支援 IE11 及更早版本。

---

## API 相容性

| 功能 | Chrome | Firefox | Safari | Edge | 備註 |
|---------|--------|---------|--------|------|-------|
| Fetch API / async/await | 55+ | 52+ | 11+ | 15+ | 所有瀏覽器支援 |
| AbortController | 66+ | 57+ | 11.1+ | 16+ | 所有瀏覽器支援 |
| IntersectionObserver | 51+ | 55+ | 12.1+ | 16+ | 用於無限捲動 |
| Optional chaining `?.` | 80+ | 74+ | 13.1+ | 80+ | 在程式碼庫中廣泛使用 |
| scroll-snap | 69+ | 68+ | 13+ | 79+ | 用於 Dock 卡片 |
| `scrollbar-gutter` | 94+ | 101+ | **16+** | 94+ | Safari 15 及更早版本不支援 |
| `inset` CSS 簡寫 | 102+ | 106+ | **16+** | 102+ | Safari 15 及更早版本不支援 |
| `backdrop-filter` | 76+ | **不支援** | 9+ | 79+ | Firefox 不支援 |
| `-webkit-backdrop-filter` | 支援 | **不支援** | 9+ | 支援 | Firefox 無替代方案 |

---

## 已知問題

### Firefox — 不支援 `backdrop-filter`

- **受影響檔案：** `dock-shell-panel.css`、`search-results-modal-nav.css`
- **症狀：** 面板模糊效果（毛玻璃效果）不渲染，背景保持透明
- **嚴重程度：** 視覺品質下降（功能不受影響）
- **計畫：** 暫未處理（未來可能為 Firefox 新增不透明背景回退）

### Safari 15 及更早版本 — 不支援 `scrollbar-gutter`、`inset`

- **受影響檔案：** `dock-cards.css`、`uxpatch-i18n-paths.css`
- **症狀：** 捲軸區域抖動和輕微的位置計算偏移
- **嚴重程度：** 輕微（版面功能正常）

---

## 現有相容性措施（良好實踐）

- 同時宣告了 `-webkit-backdrop-filter` 和標準 `backdrop-filter`
- Firefox 捲軸使用 `scrollbar-width` / `scrollbar-color`
- WebKit 捲軸使用 `-webkit-scrollbar`
- 未使用破壞性 API（`crypto.randomUUID`、`structuredClone`、`.at()` 等）

---

## 未來候選項

| 項目 | 優先順序 | 說明 |
|------|----------|-------------|
| Firefox backdrop-filter 回退 | P3 | 切換為無模糊的半透明背景 |
| `@supports` 條件查詢 | P3 | CSS 功能偵測 |
