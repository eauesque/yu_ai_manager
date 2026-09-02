# Design-Leitfaden — CSS-Design, Themes, Responsives Layout

Richtlinien und Implementierungsmuster für das Design benutzerdefinierter UIs.

## CSS-Variablensystem

Die Referenz-UI verwaltet Themes über CSS-benutzerdefinierte Eigenschaften.
Die Verwendung dieser Variablen in benutzerdefinierten UIs erleichtert den Theme-Wechsel und die Unterstützung des Dunkelmodus.

### Kern-Variablen

```css
:root {
  --bg: #f5f6f8;         /* Seitenhintergrund */
  --card: #ffffff;        /* Karten-/Panel-Hintergrund */
  --text: #222;           /* Haupttext */
  --muted: #666;          /* Untertext/Hinweise */
  --border: #e6e6e6;      /* Rahmen/Trennlinien */
  --shadow: 0 4px 14px rgba(0,0,0,0.08);  /* Kartenschatten */
  --btn-bg: #ffffff;      /* Schaltflächen-Hintergrund */
  --btn-text: #222;       /* Schaltflächen-Text */
  --btn-hover: #f6f9ff;   /* Schaltflächen-Hover */
  --accent: #2563eb;      /* Akzentfarbe (WCAG AA-konform) */
}
```

### Dunkelmodusv-Variablen

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

`color-scheme: dark` beeinflusst die Farbgebung von OS-Formularsteuerelementen (Checkboxen, Scrollleisten usw.).

### Vollständige Variablenliste

Details finden Sie unter [theming.md](../api/theming.md).

## Theme-Erstellung

### Benutzerdefiniertes Theme definieren

Themes werden durch Überschreiben von CSS-Variablen definiert, die an eine Klasse des `body`-Elements gebunden sind:

```css
/* Ocean-Theme */
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

/* Sakura-Theme (Hellmodus) */
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

### Theme anwenden

Theme-Klassen per JavaScript wechseln:

```javascript
function setTheme(themeName) {
  // Bestehende Theme-Klassen entfernen
  document.body.className = document.body.className
    .replace(/theme-\S+/g, '')
    .trim();
  if (themeName && themeName !== 'default') {
    document.body.classList.add(`theme-${themeName}`);
  }
  // Persistieren
  localStorage.setItem('customTheme', themeName);
}

// Bei Start wiederherstellen
const saved = localStorage.getItem('customTheme');
if (saved) setTheme(saved);
```

### Dunkelmodusumschalter

Dunkelmoduserkennungslogik der Referenz-UI:

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

## Responsives Design

### Breakpoints

Von der Referenz-UI verwendete Breakpoints:

| Breakpoint | Verwendung |
|----------------|------|
| `max-width: 600px` | Mobil (Hamburger-Menü, 1-spaltiges Raster) |
| `max-width: 900px` | Tablet (2-spaltiges Raster, eingeklappte Seitenleiste) |
| `min-width: 901px` | Desktop (3+ spaltiges Raster, immer sichtbare Seitenleiste) |

### Raster-Layout

Responsives Raster für Bildsuchergebnisse:

```css
.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
  padding: 16px;
}

/* Mobil: kleinere Karten */
@media (max-width: 600px) {
  .image-grid {
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 8px;
    padding: 8px;
  }
}

/* Grosse Bildschirme: mehr Platz */
@media (min-width: 1600px) {
  .image-grid {
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 16px;
  }
}
```

### Navigationsleiste

Mobilfreundliche Navigationsleiste:

```css
.navbar {
  display: flex;
  align-items: center;
  padding: 0 16px;
  height: 48px;
  background: var(--card);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 100;
}

.nav-links {
  display: flex;
  gap: 8px;
}

.hamburger { display: none; }

@media (max-width: 600px) {
  .nav-links {
    display: none;
    position: absolute;
    top: 48px;
    left: 0;
    right: 0;
    flex-direction: column;
    background: var(--card);
    border-bottom: 1px solid var(--border);
    padding: 8px;
  }
  .nav-links.open { display: flex; }
  .hamburger { display: block; }
}
```

## Komponenten-Muster

### Karten-Komponente

Grundmuster für Bildkarten:

```css
.card {
  background: var(--card);
  border-radius: 8px;
  overflow: hidden;
  box-shadow: var(--shadow);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.card:hover {
  transform: translateY(-2px);
  box-shadow: 0 12px 32px rgba(0,0,0,0.3);
}

.card img {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  display: block;
}

.card-body {
  padding: 10px 12px;
}

.card-title {
  font-size: 0.85rem;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-meta {
  font-size: 0.75rem;
  color: var(--muted);
  margin-top: 2px;
}
```

### Schaltflächen

```css
.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: var(--btn-bg);
  color: var(--btn-text);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.875rem;
  cursor: pointer;
  transition: background 0.15s;
}

.btn:hover { background: var(--btn-hover); }

/* Primär-Schaltfläche */
.btn-primary {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
.btn-primary:hover {
  filter: brightness(1.1);
}

/* Kleine Schaltfläche (Hilfsaktion) */
.btn-sm {
  padding: 4px 10px;
  font-size: 0.8rem;
}
```

### Modal

```css
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s;
}

.modal-overlay.active {
  opacity: 1;
  pointer-events: auto;
}

.modal {
  background: var(--card);
  border-radius: 12px;
  padding: 24px;
  max-width: 600px;
  width: 90%;
  max-height: 80vh;
  overflow-y: auto;
  box-shadow: 0 20px 60px rgba(0,0,0,0.5);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.modal-close {
  background: none;
  border: none;
  color: var(--muted);
  font-size: 1.5rem;
  cursor: pointer;
}
```

### Tag-Token

```css
.tag {
  display: inline-block;
  padding: 2px 8px;
  background: var(--tag-bg, #4a4a4a);
  color: var(--tag-text, #f0f0f0);
  border: 1px solid var(--tag-border, #666);
  border-radius: 4px;
  font-size: 0.75rem;
  cursor: pointer;
  transition: background 0.1s;
}

.tag:hover {
  background: var(--tag-hover-bg, #5a5a5a);
  border-color: var(--tag-hover-border, #888);
}
```

### Toast-Benachrichtigungen

```css
.toast {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%) translateY(100px);
  background: var(--card);
  color: var(--text);
  padding: 12px 24px;
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.4);
  z-index: 2000;
  opacity: 0;
  transition: transform 0.3s ease, opacity 0.3s ease;
}

.toast.show {
  transform: translateX(-50%) translateY(0);
  opacity: 1;
}
```

### Sternebewertung

```css
.star-rating {
  display: inline-flex;
  gap: 2px;
}

.star-rating .star {
  cursor: pointer;
  font-size: 1.2rem;
  color: var(--muted);
  transition: color 0.1s;
}

.star-rating .star.filled { color: #fbbf24; }
.star-rating .star:hover { color: #f59e0b; }
```

## Performance

### Lazy Loading von Bildern

```html
<img src="/api/thumbnail/${id}" loading="lazy" alt="${filename}">
```

`loading="lazy"` ist natives Browser-Lazy-Loading. Bilder werden erst geladen, wenn sie in den sichtbaren Bereich gescrollt werden.

### Thumbnail-Cache

`/api/thumbnail/<id>` gibt ETag- und 24-Stunden-Cache-Header zurück.
Der Browser cached automatisch, sodass keine zusätzliche Implementierung erforderlich ist.

### Anzeige großer Bildmengen

Bei Bibliotheken mit 150.000+ Einträgen verschlechtert sich die Performance, wenn alle gleichzeitig dem DOM hinzugefügt werden.
Es wird empfohlen, Cursor-basierte Paginierung für schrittweises Laden zu verwenden.

## Barrierefreiheit

### Farbkontrast

- Text: WCAG AA (4,5:1 oder mehr) einhalten
- Standard `--accent` `#2563eb` hat 5,17:1 auf weißem Hintergrund
- Dunkelmodusv `--accent` `#60a5fa` hat ausreichenden Kontrast auf dunklem Hintergrund

### Tastaturnavigation

```css
/* Fokusring sichtbar machen */
:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

/* Fokusring bei Nicht-Tastatur-Fokus ausblenden */
:focus:not(:focus-visible) {
  outline: none;
}
```

### Skip-Links

Die Referenz-UI platziert oben auf der Seite einen Skip-Link:

```html
<a href="#main-content" class="skip-link">Skip to main content</a>
```

```css
.skip-link {
  position: absolute;
  top: -100px;
  left: 16px;
  z-index: 9999;
  padding: 8px 16px;
  background: var(--accent);
  color: #fff;
  border-radius: 4px;
}
.skip-link:focus { top: 8px; }
```
