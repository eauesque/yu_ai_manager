# Guida alla progettazione — CSS, tema, responsive

Linee guida e pattern di implementazione per il design di un'UI personalizzata.

## Sistema di variabili CSS

L'UI di riferimento gestisce il tema usando proprietà custom CSS.
Anche l'UI personalizzata può usare queste variabili per semplificare il cambio tema e la modalità dark.

### Variabili core

```css
:root {
  --bg: #f5f6f8;         /* Sfondo pagina */
  --card: #ffffff;        /* Sfondo card e panel */
  --text: #222;           /* Testo principale */
  --muted: #666;          /* Testo secondario e hint */
  --border: #e6e6e6;      /* Border e linee divisorie */
  --shadow: 0 4px 14px rgba(0,0,0,0.08);  /* Ombra card */
  --btn-bg: #ffffff;      /* Sfondo bottone */
  --btn-text: #222;       /* Testo bottone */
  --btn-hover: #f6f9ff;   /* Bottone al passaggio */
  --accent: #2563eb;      /* Colore accento (WCAG AA compliant) */
}
```

### Variabili modalità dark

```css
body.dark {
  --bg: #0f1115;
  --card: #1b1f2a;
  --text: #e7eaf0;
  --muted: #aab2c0;
  --border: #2b3240;
  --shadow: 0 10px 26px rgba(0,0,0,0.45);
  --btn-bg: #1b2030;
  --btn-text: #e7eaf0;
  --btn-hover: #222a3d;
  --accent: #60a5fa;
  color-scheme: dark;
}
```

`color-scheme: dark` influisce sul colore dei controlli del form dell'OS (checkbox, scrollbar, ecc.).

### Elenco variabili completo

Per dettagli, vedi [theming.md](../api/theming.md).

## Creazione di un tema

### Definire un tema personalizzato

Il tema è definito sovrascrivendo le variabili CSS associate alla classe di `body`:

```css
/* Tema Ocean */
body.theme-ocean {
  --bg: #0a1628;
  --card: #132744;
  --text: #c8daf0;
  --muted: #7a9cc0;
  --border: #1e3a5f;
  --shadow: 0 8px 24px rgba(0,0,0,0.5);
  --btn-bg: #1a3050;
  --btn-text: #c8daf0;
  --btn-hover: #243d5f;
  --accent: #38bdf8;
  color-scheme: dark;
}

/* Tema Sakura (light mode) */
body.theme-sakura {
  --bg: #fff5f5;
  --card: #ffffff;
  --text: #4a3030;
  --muted: #8a7070;
  --border: #f0d0d0;
  --shadow: 0 4px 14px rgba(200,100,100,0.1);
  --accent: #e8457a;
  color-scheme: light;
}
```

### Applicare il tema

Cambia la classe tema con JavaScript:

```javascript
function setTheme(themeName) {
  // Rimuovi classe tema esistente
  document.body.className = document.body.className
    .replace(/theme-\S+/g, '')
    .trim();
  if (themeName && themeName !== 'default') {
    document.body.classList.add(`theme-${themeName}`);
  }
  // Persistenza
  localStorage.setItem('customTheme', themeName);
}

// Ripristina al caricamento
const saved = localStorage.getItem('customTheme');
if (saved) setTheme(saved);
```

### Cambio modalità dark

Logica di determinazione dark mode dall'UI di riferimento:

```javascript
function initDarkMode() {
  const saved = localStorage.getItem('darkMode');
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  const isDark = saved !== null ? saved === 'true' : prefersDark;
  document.body.classList.toggle('dark', isDark);
}

function toggleDarkMode() {
  const isDark = document.body.classList.toggle('dark');
  localStorage.setItem('darkMode', String(isDark));
}

initDarkMode();
```

## Design responsive

### Breakpoint

Breakpoint usati dall'UI di riferimento:

| Breakpoint | Utilizzo |
|----------------|------|
| `max-width: 600px` | Mobile (menu hamburger, griglia 1 colonna) |
| `max-width: 900px` | Tablet (griglia 2 colonne, sidebar comprimibile) |
| `min-width: 901px` | Desktop (griglia 3+ colonne, sidebar sempre visibile) |

### Layout griglia

Griglia responsive per risultati di ricerca immagini:

```css
.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
  padding: 16px;
}

@media (max-width: 600px) {
  .image-grid {
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 8px;
  }
}
```

### Flexbox layout

Per navigazione e intestazione:

```css
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px;
  flex-wrap: wrap;
  gap: 16px;
}

.header nav {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

@media (max-width: 600px) {
  .header {
    flex-direction: column;
    align-items: stretch;
  }
}
```

## Componenti comuni

### Bottone

```css
.btn {
  padding: 10px 16px;
  background: var(--accent);
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 1rem;
  cursor: pointer;
  transition: opacity 0.2s;
}

.btn:hover {
  opacity: 0.9;
}

.btn:active {
  opacity: 0.8;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--btn-bg);
  color: var(--text);
  border: 1px solid var(--border);
}
```

### Input

```css
input, textarea, select {
  padding: 10px;
  background: var(--card);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 1rem;
  font-family: inherit;
}

input:focus, textarea:focus, select:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(var(--accent-rgb), 0.1);
}
```

### Card

```css
.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  box-shadow: var(--shadow);
  transition: transform 0.2s, box-shadow 0.2s;
}

.card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}
```

## Accessibility

### Contrasto colore

Assicurati che il contrasto tra testo e sfondo sia di almeno 4.5:1 (WCAG AA):

```css
/* Buono: #2563eb su #f5f6f8 (contrast ratio ~7:1) */
/* Non buono: #999 su #f0f0f0 (contrast ratio ~2:1) */
```

### Focus states

Rendi sempre visibile lo stato focus per la navigazione tastiera:

```css
button:focus-visible,
a:focus-visible,
input:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
```

### Etichette form

Associa sempre etichette agli input:

```html
<label for="search-input">Search</label>
<input id="search-input" type="text" placeholder="...">
```

## Ottimizzazioni di performance

### Critical CSS

Includi CSS critico (layout, base) nel `<head>`:

```html
<head>
  <style>
    body { margin: 0; padding: 0; font-family: system-ui; }
    main { padding: 20px; max-width: 1400px; margin: 0 auto; }
  </style>
  <link rel="stylesheet" href="/static/style.css">
</head>
```

### Lazy loading

Carica CSS supplementari in modo lazy:

```html
<link rel="preload" href="/static/theme.css" as="style" onload="this.onload=null;this.rel='stylesheet'">
```

### Image optimization

Usa sempre `loading="lazy"` per immagini non critical:

```html
<img src="/api/thumbnail/42" loading="lazy" alt="thumbnail">
```
