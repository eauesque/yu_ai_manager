# 佈景主題 — CSS Custom Properties

參考 UI（`ui/default/`）使用的 CSS 自訂屬性清單。
自訂 UI 可以透過重新定義這些變數來更改現有元件的外觀。

來源：`ui/default/static/css/base/base-theme.css`

## 核心變數（`:root` / `body.dark`）

| 變數 | 淺色 | 深色 | 用途 |
|----------|-------|------|---------|
| `--bg` | `#f5f6f8` | `#0f1115` | 頁面背景 |
| `--card` | `#ffffff` | `#1b1f2a` | 卡片/面板背景 |
| `--text` | `#222` | `#e7eaf0` | 主要文字 |
| `--muted` | `#666` | `#aab2c0` | 輔助文字/提示 |
| `--border` | `#e6e6e6` | `#2b3240` | 邊框/分隔線 |
| `--shadow` | `0 4px 14px rgba(0,0,0,0.08)` | `0 10px 26px rgba(0,0,0,0.45)` | 卡片陰影 |
| `--btn-bg` | `#ffffff` | `#1b2030` | 按鈕背景 |
| `--btn-text` | `#222` | `#e7eaf0` | 按鈕文字 |
| `--btn-hover` | `#f6f9ff` | `#222a3d` | 按鈕懸停 |
| `--tooltip-bg` | `rgba(0,0,0,0.85)` | `rgba(0,0,0,0.92)` | 工具提示背景 |
| `--tooltip-text` | `#fff` | `#fff` | 工具提示文字 |
| `--accent` | `#2563eb` | `#60a5fa` | 強調色（連結、按鈕高亮） |

## 深色模式變數

### 標籤代幣

| 變數 | 值 | 用途 |
|----------|-------|---------|
| `--tag-bg` | `#4a4a4a` | 標籤背景 |
| `--tag-text` | `#f0f0f0` | 標籤文字 |
| `--tag-border` | `#666` | 標籤邊框 |
| `--tag-hover-bg` | `#5a5a5a` | 標籤懸停背景 |
| `--tag-hover-border` | `#888` | 標籤懸停邊框 |
| `--tag-focus-ring` | `#60a5fa` | 標籤聚焦環 |

### 標籤分類變體

| 變數 | 用途 |
|----------|---------|
| `--tag-ns-*` | 命名空間標籤（bg、border、text） |
| `--tag-wh-*` | 高權重標籤 |
| `--tag-wl-*` | 低權重標籤 |
| `--tag-we-*` | 強調權重標籤 |

### 負面提示詞

| 變數 | 值 | 用途 |
|----------|-------|---------|
| `--neg-prompt-bg` | `#2d2424` | 負面提示詞背景 |
| `--neg-prompt-border` | `#fc8181` | 負面提示詞邊框 |
| `--neg-heading` | `#fc8181` | 負面標題 |

### 手風琴

| 變數 | 值 | 用途 |
|----------|-------|---------|
| `--accordion-bg` | `#252525` | 手風琴背景 |
| `--accordion-border` | `#3a3a3a` | 手風琴邊框 |
| `--accordion-header-bg` | `#2a2a2a` | 標題背景 |
| `--accordion-header-text` | `#e0e0e0` | 標題文字 |

## 佈景主題類別

| 類別 | 說明 |
|-------|-------------|
| `body.dark` | 深色模式 |
| `body.theme-retro` | 復古霓虹佈景主題（科乐美密碼） |
| `body.theme-glow` | 自訂發光效果 |

## 套用佈景主題

在自訂 UI 中變更佈景主題：

```css
/* 自訂佈景主題範例 */
body.theme-ocean {
  --bg: #0a1628;
  --card: #132744;
  --text: #c8daf0;
  --accent: #38bdf8;
  color-scheme: dark;
}
```

透過在 `body` 元素新增類別來套用佈景主題。
深色模式中的 `color-scheme: dark` 屬性會影響作業系統表單控制項的顏色。
