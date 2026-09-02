# Guía de diseño — Arquitectura CSS, temas y diseño responsivo

Directrices y patrones de implementación para el diseño de la UI personalizada.

## Sistema de variables CSS

La UI de referencia gestiona los temas mediante propiedades personalizadas de CSS.
Al usar estas mismas variables en su UI personalizada, facilita el cambio de tema y el soporte de modo oscuro.

### Variables principales

```css
:root {
  --bg: #f5f6f8;         /* Fondo de la página */
  --card: #ffffff;        /* Fondo de tarjetas y paneles */
  --text: #222;           /* Texto principal */
  --muted: #666;          /* Texto secundario / pistas */
  --border: #e6e6e6;      /* Bordes / separadores */
  --shadow: 0 4px 14px rgba(0,0,0,0.08);  /* Sombra de tarjeta */
  --btn-bg: #ffffff;      /* Fondo de botón */
  --btn-text: #222;       /* Texto de botón */
  --btn-hover: #f6f9ff;   /* Hover de botón */
  --accent: #2563eb;      /* Color de acento (cumple WCAG AA) */
}
```

### Variables del modo oscuro

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

`color-scheme: dark` afecta al color de los controles de formulario del sistema operativo (casillas, barras de desplazamiento, etc.).

### Lista completa de variables

Consulte los detalles en [theming.md](../api/theming.md).

## Creación de temas

### Definir un tema personalizado

Un tema se define sobrescribiendo las variables CSS asociadas a una clase del elemento `body`:

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

/* Tema Sakura (modo claro) */
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

### Aplicar el tema

Se alterna la clase del tema desde JavaScript:

```javascript
function setTheme(themeName) {
  // Eliminar las clases de tema existentes
  document.body.className = document.body.className
    .replace(/theme-\S+/g, '')
    .trim();
  if (themeName && themeName !== 'default') {
    document.body.classList.add(`theme-${themeName}`);
  }
  // Persistencia
  localStorage.setItem('customTheme', themeName);
}

// Restaurar al arrancar
const saved = localStorage.getItem('customTheme');
if (saved) setTheme(saved);
```

### Alternar el modo oscuro

Lógica de detección del modo oscuro de la UI de referencia:

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

## Diseño responsivo

### Puntos de corte

Puntos de corte usados en la UI de referencia:

| Punto de corte | Uso |
|----------------|------|
| `max-width: 600px` | Móvil (menú hamburguesa, cuadrícula de 1 columna) |
| `max-width: 900px` | Tableta (cuadrícula de 2 columnas, barra lateral plegada) |
| `min-width: 901px` | Escritorio (cuadrícula de 3 o más columnas, barra lateral visible) |

### Disposición en cuadrícula

Cuadrícula responsiva para los resultados de búsqueda de imágenes:

```css
.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
  padding: 16px;
}

/* Móvil: tarjetas más pequeñas */
@media (max-width: 600px) {
  .image-grid {
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 8px;
    padding: 8px;
  }
}

/* Pantalla grande: más margen */
@media (min-width: 1600px) {
  .image-grid {
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 16px;
  }
}
```

### Barra de navegación

Barra de navegación adaptada a móvil:

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

## Patrones de componente

### Componente de tarjeta

Patrón básico de tarjeta de imagen:

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

### Botón

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

/* Botón primario */
.btn-primary {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
.btn-primary:hover {
  filter: brightness(1.1);
}

/* Botón pequeño (acciones secundarias) */
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

### Ficha de etiqueta

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

### Notificación tipo toast

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

```javascript
function showToast(message, duration = 3000) {
  const el = document.getElementById('toast');
  el.textContent = message;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), duration);
}
```

### Valoración con estrellas

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

```javascript
function createStarRating(fileId, currentRating = 0) {
  const container = document.createElement('div');
  container.className = 'star-rating';
  for (let i = 1; i <= 5; i++) {
    const star = document.createElement('span');
    star.className = 'star' + (i <= currentRating ? ' filled' : '');
    star.textContent = '★';
    star.onclick = async () => {
      const newRating = i === currentRating ? 0 : i;
      await api('/api/ratings/set', {
        method: 'POST',
        body: JSON.stringify({ file_id: fileId, rating: newRating }),
      });
      // Actualizar la UI
      container.querySelectorAll('.star').forEach((s, idx) => {
        s.classList.toggle('filled', idx < newRating);
      });
    };
    container.appendChild(star);
  }
  return container;
}
```

## Rendimiento

### Carga diferida de imágenes

```html
<img src="/api/thumbnail/${id}" loading="lazy" alt="${filename}">
```

`loading="lazy"` es la carga diferida nativa del navegador. La imagen se carga cuando entra en el área visible por scroll.

### Caché de miniaturas

`/api/thumbnail/<id>` devuelve cabeceras ETag y de caché de 24 horas.
El navegador cachea automáticamente, por lo que no se requiere implementación adicional.

### Mostrar grandes cantidades de imágenes

En librerías con más de 150 000 elementos, añadir todos al DOM de una vez degrada el rendimiento.
Se recomienda cargar progresivamente con paginación basada en cursor:

```javascript
let nextCursor = null;
let loading = false;

async function loadMore() {
  if (loading) return;
  loading = true;
  const params = new URLSearchParams({ limit: '50' });
  if (nextCursor) params.set('cursor', nextCursor);
  const res = await fetch(`/api/search?${params}`);
  const json = await res.json();
  const items = json.results || json.data?.results || [];
  nextCursor = json.next_cursor || json.data?.next_cursor || null;

  const grid = document.getElementById('results');
  items.forEach(f => {
    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML = `<img src="/api/thumbnail/${f.id}" loading="lazy">`;
    grid.appendChild(card);
  });
  loading = false;
}

// Detectar el scroll con Intersection Observer
const sentinel = document.getElementById('sentinel');
new IntersectionObserver(entries => {
  if (entries[0].isIntersecting && nextCursor) loadMore();
}).observe(sentinel);
```

## Accesibilidad

### Contraste de color

- Texto: mantener WCAG AA (4,5:1 o superior)
- El `--accent` por defecto `#2563eb` tiene 5,17:1 sobre fondo blanco
- El `--accent` del modo oscuro `#60a5fa` ofrece contraste suficiente sobre fondo oscuro

### Uso por teclado

```css
/* Visualizar el anillo de foco */
:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

/* Ocultar el anillo para focos no provocados por teclado */
:focus:not(:focus-visible) {
  outline: none;
}
```

### Skip link

La UI de referencia coloca un enlace de salto en la parte superior de la pantalla:

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
