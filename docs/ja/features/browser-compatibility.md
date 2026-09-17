# ブラウザ互換性レポート

**調査日:** 2026-02-23

## 対応ブラウザ（推奨）

| ブラウザ | 最小バージョン | 全機能対応バージョン |
|----------|---------------|-------------------|
| Chrome   | 80+           | 94+               |
| Firefox  | 74+           | 101+              |
| Safari   | 13.1+         | 16+               |
| Edge     | 80+           | 94+               |

IE11 および旧バージョンは非対応。

---

## 使用 API の互換性

| 機能 | Chrome | Firefox | Safari | Edge | 備考 |
|------|--------|---------|--------|------|------|
| Fetch API / async/await | 55+ | 52+ | 11+ | 15+ | 全ブラウザ対応 |
| AbortController | 66+ | 57+ | 11.1+ | 16+ | 全ブラウザ対応 |
| IntersectionObserver | 51+ | 55+ | 12.1+ | 16+ | 無限スクロールで使用 |
| Optional chaining `?.` | 80+ | 74+ | 13.1+ | 80+ | コード全域で多用 |
| scroll-snap | 69+ | 68+ | 13+ | 79+ | ドックカードで使用 |
| `scrollbar-gutter` | 94+ | 101+ | **16+** | 94+ | Safari 15 以前で非対応 |
| `inset` CSS 短縮形 | 102+ | 106+ | **16+** | 102+ | Safari 15 以前で非対応 |
| `backdrop-filter` | 76+ | **非対応** | 9+ | 79+ | Firefox で非対応 |
| `-webkit-backdrop-filter` | ✓ | **非対応** | 9+ | ✓ | Firefox に代替なし |

---

## 既知の問題

### 🔴 Firefox — `backdrop-filter` 非対応

- **影響箇所:** `dock-shell-panel.css`, `search-results-modal-nav.css`
- **症状:** パネルのぼかし効果（グラスモーフィズム）が表示されず、背景が透過のままになる
- **重大度:** 表示品質の劣化（機能的には動作する）
- **対応方針:** 未対応（Firefox 向け不透明背景フォールバックを将来追加可）

### 🟡 Safari 15 以前 — `scrollbar-gutter`, `inset` 非対応

- **影響箇所:** `dock-cards.css`, `uxpatch-i18n-paths.css`
- **症状:** スクロールバー領域の揺れ、位置計算の微小なずれ
- **重大度:** 軽微（レイアウトは機能する）

---

## 既存の互換性対応（良好な実装）

- `-webkit-backdrop-filter` と標準 `backdrop-filter` を併記済み
- Firefox 向けスクロールバー: `scrollbar-width` / `scrollbar-color` を使用
- WebKit 向けスクロールバー: `-webkit-scrollbar` を使用
- 破壊的 API（`crypto.randomUUID`, `structuredClone`, `.at()` 等）は不使用

---

## 将来対応候補

| 項目 | 優先度 | 内容 |
|------|--------|------|
| Firefox backdrop-filter フォールバック | P3 | ぼかしなしの半透明背景に切り替え |
| `@supports` 条件クエリ追加 | P3 | CSS での機能検出 |
