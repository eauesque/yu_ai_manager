# Theming — CSS-Benutzerdefinierte Eigenschaften

Dies ist eine Liste der CSS-Benutzerdefinieren Eigenschaften, die in der Referenz-UI (`ui/default/`) verwendet werden.
Eine benutzerdefinierte UI kann das Erscheinungsbild der bestehenden Komponenten ändern, indem diese Variablen neu definiert werden.

Quelle: `ui/default/static/css/base/base-theme.css`

## Kern-Variablen (`:root` / `body.dark`)

| Variable | Hell | Dunkel | Zweck |
|----------|------|--------|---------|
| `--bg` | `#f5f6f8` | `#0f1115` | Seiten-Hintergrund |
| `--card` | `#ffffff` | `#1b1f2a` | Karten-/Panel-Hintergrund |
| `--text` | `#222` | `#e7eaf0` | Haupttext |
| `--muted` | `#666` | `#aab2c0` | Untertext/Hinweise |
| `--border` | `#e6e6e6` | `#2b3240` | Grenzen/Trennlinien |
| `--shadow` | `0 4px 14px rgba(0,0,0,0.08)` | `0 10px 26px rgba(0,0,0,0.45)` | Kartenschatten |
| `--btn-bg` | `#ffffff` | `#1b2030` | Button-Hintergrund |
| `--btn-text` | `#222` | `#e7eaf0` | Button-Text |
| `--btn-hover` | `#f6f9ff` | `#222a3d` | Button-Hover |
| `--tooltip-bg` | `rgba(0,0,0,0.85)` | `rgba(0,0,0,0.92)` | Tooltip-Hintergrund |
| `--tooltip-text` | `#fff` | `#fff` | Tooltip-Text |
| `--accent` | `#2563eb` | `#60a5fa` | Akzentfarbe (Links, Button-Highlights) |

## Variablen für Dunkelmodus

### Tag-Tokens

| Variable | Wert | Zweck |
|----------|------|---------|
| `--tag-bg` | `#4a4a4a` | Tag-Hintergrund |
| `--tag-text` | `#f0f0f0` | Tag-Text |
| `--tag-border` | `#666` | Tag-Grenze |
| `--tag-hover-bg` | `#5a5a5a` | Tag-Hover-Hintergrund |
| `--tag-hover-border` | `#888` | Tag-Hover-Grenze |
| `--tag-focus-ring` | `#60a5fa` | Tag-Focus-Ring |

### Tag-Kategorie-Varianten

| Variable | Zweck |
|----------|---------|
| `--tag-ns-*` | Namespace-Tags (bg, border, text) |
| `--tag-wh-*` | High-Weight-Tags |
| `--tag-wl-*` | Low-Weight-Tags |
| `--tag-we-*` | Hervorgehobene-Weight-Tags |

### Negatives Prompt

| Variable | Wert | Zweck |
|----------|------|---------|
| `--neg-prompt-bg` | `#2d2424` | Negativer Prompt-Hintergrund |
| `--neg-prompt-border` | `#fc8181` | Negativer Prompt-Grenze |
| `--neg-heading` | `#fc8181` | Negative Überschrift |

### Akkordeon

| Variable | Wert | Zweck |
|----------|------|---------|
| `--accordion-bg` | `#252525` | Akkordeon-Hintergrund |
| `--accordion-border` | `#3a3a3a` | Akkordeon-Grenze |
| `--accordion-header-bg` | `#2a2a2a` | Header-Hintergrund |
| `--accordion-header-text` | `#e0e0e0` | Header-Text |

## Theme-Klassen

| Klasse | Beschreibung |
|--------|-------------|
| `body.dark` | Dunkelmodus |
| `body.theme-retro` | Retro-Neon-Theme (Konami-Code) |
| `body.theme-glow` | Benutzerdefinierter Glow-Effekt |

## Anwendung von Themes

Ändern Sie das Theme in einer benutzerdefinierten UI:

```css
/* Benutzerdefiniertes Theme-Beispiel */
body.theme-ocean {
  --bg: #0a1628;
  --card: #132744;
  --text: #c8daf0;
  --accent: #38bdf8;
  color-scheme: dark;
}
```

Das Theme wird wirksam, indem eine Klasse zum `body`-Element hinzugefügt wird.
Die `color-scheme: dark`-Eigenschaft im Dunkelmodus beeinflusst die Farben der OS-Formularsteuerelemente.
