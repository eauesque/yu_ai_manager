# 主题 — CSS Custom Properties

参考 UI（`ui/default/`）使用的 CSS 自定义属性列表。
自定义 UI 可以通过重新定义这些变量来更改现有组件的外观。

来源：`ui/default/static/css/base/base-theme.css`

## 核心变量（`:root` / `body.dark`）

| 变量 | 浅色 | 深色 | 用途 |
|----------|-------|------|---------|
| `--bg` | `#f5f6f8` | `#0f1115` | 页面背景 |
| `--card` | `#ffffff` | `#1b1f2a` | 卡片/面板背景 |
| `--text` | `#222` | `#e7eaf0` | 主要文本 |
| `--muted` | `#666` | `#aab2c0` | 辅助文本/提示 |
| `--border` | `#e6e6e6` | `#2b3240` | 边框/分隔线 |
| `--shadow` | `0 4px 14px rgba(0,0,0,0.08)` | `0 10px 26px rgba(0,0,0,0.45)` | 卡片阴影 |
| `--btn-bg` | `#ffffff` | `#1b2030` | 按钮背景 |
| `--btn-text` | `#222` | `#e7eaf0` | 按钮文本 |
| `--btn-hover` | `#f6f9ff` | `#222a3d` | 按钮悬停 |
| `--tooltip-bg` | `rgba(0,0,0,0.85)` | `rgba(0,0,0,0.92)` | 工具提示背景 |
| `--tooltip-text` | `#fff` | `#fff` | 工具提示文本 |
| `--accent` | `#2563eb` | `#60a5fa` | 强调色（链接、按钮高亮） |

## 深色模式变量

### 标签令牌

| 变量 | 值 | 用途 |
|----------|-------|---------|
| `--tag-bg` | `#4a4a4a` | 标签背景 |
| `--tag-text` | `#f0f0f0` | 标签文本 |
| `--tag-border` | `#666` | 标签边框 |
| `--tag-hover-bg` | `#5a5a5a` | 标签悬停背景 |
| `--tag-hover-border` | `#888` | 标签悬停边框 |
| `--tag-focus-ring` | `#60a5fa` | 标签聚焦环 |

### 标签分类变体

| 变量 | 用途 |
|----------|---------|
| `--tag-ns-*` | 命名空间标签（bg、border、text） |
| `--tag-wh-*` | 高权重标签 |
| `--tag-wl-*` | 低权重标签 |
| `--tag-we-*` | 强调权重标签 |

### 负面提示词

| 变量 | 值 | 用途 |
|----------|-------|---------|
| `--neg-prompt-bg` | `#2d2424` | 负面提示词背景 |
| `--neg-prompt-border` | `#fc8181` | 负面提示词边框 |
| `--neg-heading` | `#fc8181` | 负面标题 |

### 手风琴

| 变量 | 值 | 用途 |
|----------|-------|---------|
| `--accordion-bg` | `#252525` | 手风琴背景 |
| `--accordion-border` | `#3a3a3a` | 手风琴边框 |
| `--accordion-header-bg` | `#2a2a2a` | 标题背景 |
| `--accordion-header-text` | `#e0e0e0` | 标题文本 |

## 主题类

| 类 | 说明 |
|-------|-------------|
| `body.dark` | 深色模式 |
| `body.theme-retro` | 复古霓虹主题（科乐美密码） |
| `body.theme-glow` | 自定义发光效果 |

## 应用主题

在自定义 UI 中更改主题：

```css
/* 自定义主题示例 */
body.theme-ocean {
  --bg: #0a1628;
  --card: #132744;
  --text: #c8daf0;
  --accent: #38bdf8;
  color-scheme: dark;
}
```

通过向 `body` 元素添加类来应用主题。
深色模式中的 `color-scheme: dark` 属性会影响操作系统表单控件的颜色。
