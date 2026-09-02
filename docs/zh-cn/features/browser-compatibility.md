# 浏览器兼容性报告

**调查日期：** 2026-02-23

## 支持的浏览器（推荐）

| 浏览器 | 最低版本 | 完整功能版本 |
|----------|----------------|---------------------|
| Chrome   | 80+            | 94+                 |
| Firefox  | 74+            | 101+                |
| Safari   | 13.1+          | 16+                 |
| Edge     | 80+            | 94+                 |

不支持 IE11 及更早版本。

---

## API 兼容性

| 功能 | Chrome | Firefox | Safari | Edge | 备注 |
|---------|--------|---------|--------|------|-------|
| Fetch API / async/await | 55+ | 52+ | 11+ | 15+ | 所有浏览器支持 |
| AbortController | 66+ | 57+ | 11.1+ | 16+ | 所有浏览器支持 |
| IntersectionObserver | 51+ | 55+ | 12.1+ | 16+ | 用于无限滚动 |
| Optional chaining `?.` | 80+ | 74+ | 13.1+ | 80+ | 在代码库中广泛使用 |
| scroll-snap | 69+ | 68+ | 13+ | 79+ | 用于 Dock 卡片 |
| `scrollbar-gutter` | 94+ | 101+ | **16+** | 94+ | Safari 15 及更早版本不支持 |
| `inset` CSS 简写 | 102+ | 106+ | **16+** | 102+ | Safari 15 及更早版本不支持 |
| `backdrop-filter` | 76+ | **不支持** | 9+ | 79+ | Firefox 不支持 |
| `-webkit-backdrop-filter` | 支持 | **不支持** | 9+ | 支持 | Firefox 无替代方案 |

---

## 已知问题

### Firefox — 不支持 `backdrop-filter`

- **受影响文件：** `dock-shell-panel.css`、`search-results-modal-nav.css`
- **症状：** 面板模糊效果（毛玻璃效果）不渲染，背景保持透明
- **严重程度：** 视觉质量下降（功能不受影响）
- **计划：** 暂未处理（未来可能为 Firefox 添加不透明背景回退）

### Safari 15 及更早版本 — 不支持 `scrollbar-gutter`、`inset`

- **受影响文件：** `dock-cards.css`、`uxpatch-i18n-paths.css`
- **症状：** 滚动条区域抖动和轻微的位置计算偏移
- **严重程度：** 轻微（布局功能正常）

---

## 现有兼容性措施（良好实践）

- 同时声明了 `-webkit-backdrop-filter` 和标准 `backdrop-filter`
- Firefox 滚动条使用 `scrollbar-width` / `scrollbar-color`
- WebKit 滚动条使用 `-webkit-scrollbar`
- 未使用破坏性 API（`crypto.randomUUID`、`structuredClone`、`.at()` 等）

---

## 未来候选项

| 项目 | 优先级 | 说明 |
|------|----------|-------------|
| Firefox backdrop-filter 回退 | P3 | 切换为无模糊的半透明背景 |
| `@supports` 条件查询 | P3 | CSS 功能检测 |
