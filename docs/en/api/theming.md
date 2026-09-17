# Theming — CSS Custom Properties

This is a list of CSS custom properties used in the reference UI (`ui/default/`).
A custom UI can override the appearance of existing components by redefining these variables.

Source: `ui/default/static/css/base/base-theme.css`

## Core Variables (`:root` / `body.dark`)

| Variable | Light | Dark | Purpose |
|----------|-------|------|---------|
| `--bg` | `#f5f6f8` | `#0f1115` | Page background |
| `--card` | `#ffffff` | `#1b1f2a` | Card/panel background |
| `--text` | `#222` | `#e7eaf0` | Main text |
| `--muted` | `#666` | `#aab2c0` | Subtext/hints |
| `--border` | `#e6e6e6` | `#2b3240` | Borders/dividers |
| `--shadow` | `0 4px 14px rgba(0,0,0,0.08)` | `0 10px 26px rgba(0,0,0,0.45)` | Card shadow |
| `--btn-bg` | `#ffffff` | `#1b2030` | Button background |
| `--btn-text` | `#222` | `#e7eaf0` | Button text |
| `--btn-hover` | `#f6f9ff` | `#222a3d` | Button hover |
| `--tooltip-bg` | `rgba(0,0,0,0.85)` | `rgba(0,0,0,0.92)` | Tooltip background |
| `--tooltip-text` | `#fff` | `#fff` | Tooltip text |
| `--accent` | `#2563eb` | `#60a5fa` | Accent color (links, button highlights) |

## Dark Mode Variables

### Tag Tokens

| Variable | Value | Purpose |
|----------|-------|---------|
| `--tag-bg` | `#4a4a4a` | Tag background |
| `--tag-text` | `#f0f0f0` | Tag text |
| `--tag-border` | `#666` | Tag border |
| `--tag-hover-bg` | `#5a5a5a` | Tag hover background |
| `--tag-hover-border` | `#888` | Tag hover border |
| `--tag-focus-ring` | `#60a5fa` | Tag focus ring |

### Tag Category Variants

| Variable | Purpose |
|----------|---------|
| `--tag-ns-*` | Namespace tags (bg, border, text) |
| `--tag-wh-*` | High-weight tags |
| `--tag-wl-*` | Low-weight tags |
| `--tag-we-*` | Emphasized-weight tags |

### Negative Prompt

| Variable | Value | Purpose |
|----------|-------|---------|
| `--neg-prompt-bg` | `#2d2424` | Negative prompt background |
| `--neg-prompt-border` | `#fc8181` | Negative prompt border |
| `--neg-heading` | `#fc8181` | Negative heading |

### Accordion

| Variable | Value | Purpose |
|----------|-------|---------|
| `--accordion-bg` | `#252525` | Accordion background |
| `--accordion-border` | `#3a3a3a` | Accordion border |
| `--accordion-header-bg` | `#2a2a2a` | Header background |
| `--accordion-header-text` | `#e0e0e0` | Header text |

## Theme Classes

| Class | Description |
|-------|-------------|
| `body.dark` | Dark mode |
| `body.theme-retro` | Retro neon theme (Konami code) |
| `body.theme-glow` | Custom glow effect |

## Applying Themes

To change the theme in a custom UI:

```css
/* Custom theme example */
body.theme-ocean {
  --bg: #0a1628;
  --card: #132744;
  --text: #c8daf0;
  --accent: #38bdf8;
  color-scheme: dark;
}
```

The theme takes effect by adding a class to the `body` element.
The `color-scheme: dark` property in dark mode affects OS form control colors.
