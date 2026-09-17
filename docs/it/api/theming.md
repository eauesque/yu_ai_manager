# Theming — Proprietà personalizzate CSS

Questo è un elenco di proprietà personalizzate CSS utilizzate nell'interfaccia utente di riferimento (`ui/default/`).
Un'interfaccia utente personalizzata può sovrascrivere l'aspetto dei componenti esistenti ridefinendo queste variabili.

Fonte: `ui/default/static/css/base/base-theme.css`

## Variabili core (`:root` / `body.dark`)

| Variabile | Light | Dark | Scopo |
|----------|-------|------|---------|
| `--bg` | `#f5f6f8` | `#0f1115` | Sfondo della pagina |
| `--card` | `#ffffff` | `#1b1f2a` | Sfondo della scheda/pannello |
| `--text` | `#222` | `#e7eaf0` | Testo principale |
| `--muted` | `#666` | `#aab2c0` | Subtesto/hint |
| `--border` | `#e6e6e6` | `#2b3240` | Bordi/divisori |
| `--shadow` | `0 4px 14px rgba(0,0,0,0.08)` | `0 10px 26px rgba(0,0,0,0.45)` | Ombra della scheda |
| `--btn-bg` | `#ffffff` | `#1b2030` | Sfondo del pulsante |
| `--btn-text` | `#222` | `#e7eaf0` | Testo del pulsante |
| `--btn-hover` | `#f6f9ff` | `#222a3d` | Passaggio del mouse del pulsante |
| `--tooltip-bg` | `rgba(0,0,0,0.85)` | `rgba(0,0,0,0.92)` | Sfondo del tooltip |
| `--tooltip-text` | `#fff` | `#fff` | Testo del tooltip |
| `--accent` | `#2563eb` | `#60a5fa` | Colore di accento (link, evidenziazioni pulsante) |

## Variabili della modalità scura

### Token tag

| Variabile | Valore | Scopo |
|----------|-------|---------|
| `--tag-bg` | `#4a4a4a` | Sfondo del tag |
| `--tag-text` | `#f0f0f0` | Testo del tag |
| `--tag-border` | `#666` | Bordo del tag |
| `--tag-hover-bg` | `#5a5a5a` | Sfondo al passaggio del mouse del tag |
| `--tag-hover-border` | `#888` | Bordo al passaggio del mouse del tag |
| `--tag-focus-ring` | `#60a5fa` | Anello di focus del tag |

### Varianti di categoria tag

| Variabile | Scopo |
|----------|---------|
| `--tag-ns-*` | Tag di namespace (bg, border, text) |
| `--tag-wh-*` | Tag ad alto peso |
| `--tag-wl-*` | Tag a basso peso |
| `--tag-we-*` | Tag di peso enfatizzato |

### Prompt negativo

| Variabile | Valore | Scopo |
|----------|-------|---------|
| `--neg-prompt-bg` | `#2d2424` | Sfondo del prompt negativo |
| `--neg-prompt-border` | `#fc8181` | Bordo del prompt negativo |
| `--neg-heading` | `#fc8181` | Intestazione negativa |

### Accordion

| Variabile | Valore | Scopo |
|----------|-------|---------|
| `--accordion-bg` | `#252525` | Sfondo dell'accordion |
| `--accordion-border` | `#3a3a3a` | Bordo dell'accordion |
| `--accordion-header-bg` | `#2a2a2a` | Sfondo dell'intestazione |
| `--accordion-header-text` | `#e0e0e0` | Testo dell'intestazione |

## Classi tema

| Classe | Descrizione |
|-------|-------------|
| `body.dark` | Modalità scura |
| `body.theme-retro` | Tema neon retrò (codice Konami) |
| `body.theme-glow` | Effetto glow personalizzato |

## Applicazione di temi

Per cambiare il tema in un'interfaccia utente personalizzata:

```css
/* Esempio di tema personalizzato */
body.theme-ocean {
  --bg: #0a1628;
  --card: #132744;
  --text: #c8daf0;
  --accent: #38bdf8;
  color-scheme: dark;
}
```

Il tema entra in vigore aggiungendo una classe all'elemento `body`.
La proprietà `color-scheme: dark` in modalità scura influenza i colori dei controlli modulo del sistema operativo.
